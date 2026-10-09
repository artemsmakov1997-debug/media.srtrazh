"""Scheduled feed discovery → full article → persisted analysis."""

from dataclasses import replace
import gzip
import json
import signal
import threading

from .analysis import analyze
from .extraction import FeedEntry, extract_article, parse_feed
from .network import FetchError, Response, SourceClient
from .sources import SOURCES, normalize_url
from .storage import Store, collection_lock, utcnow


def selected_sources(ids=None, feed_overrides=None):
    selected = list(dict.fromkeys(ids or SOURCES))
    if set(selected) - SOURCES.keys():
        raise ValueError("Допустимые источники: rt, tass, ria.")
    overrides = feed_overrides or {}
    if set(overrides) - set(selected):
        raise ValueError("RSS-переопределения допустимы только для выбранных источников.")
    return [replace(SOURCES[key], feed_url=normalize_url(overrides[key], SOURCES[key]))
            if key in overrides else SOURCES[key] for key in selected]


def collect_once(store, sources=None, limit=5, revisit_seconds=3600,
                 client_factory=SourceClient, now=utcnow, log=None, stop_event=None):
    if not 1 <= limit <= 100:
        raise ValueError("Лимит загрузки должен быть от 1 до 100 статей на источник.")
    if revisit_seconds < 300:
        raise ValueError("Повторная загрузка статьи допускается не чаще раза в 300 секунд.")
    sources = sources or list(SOURCES.values())
    run_id = store.start_run(now())
    summary = {"run_id": run_id, "success": True, "sources": {}}
    for source in sources:
        if stop_event is not None and stop_event.is_set():
            summary["success"] = False
            summary["interrupted"] = True
            break
        result = {"feed_ok": False, "discovered": 0, "fetched": 0, "new_revisions": 0,
                  "new_analyses": 0, "unchanged": 0, "failed": 0, "errors": []}
        retry_at = store.source_retry_at(source, now())
        if retry_at:
            result["deferred_until"] = retry_at
            summary["success"] = False
            summary["sources"][source.id] = result
            continue
        client = client_factory(source)
        retry_after = 0
        try:
            response = client.get_feed()
            entries = parse_feed(response.data, source)
            result["feed_ok"] = True
            result["feed_entries"] = len(entries)
            result["discovered"] = store.discover(source.id, entries, now())
            access_error = getattr(client, "robots_error", None)
            if access_error is not None:
                result["article_access_error"] = str(access_error)
                result["errors"].append({"url": f"https://{source.host}/robots.txt", "error": str(access_error)})
                articles = []
            else:
                articles = store.due(source.id, now(), limit)
            for article in articles:
                if stop_event is not None and stop_event.is_set():
                    summary["success"] = False
                    summary["interrupted"] = True
                    break
                try:
                    response = client.get(article["url"])
                    if response.content_type not in {"text/html", "application/xhtml+xml"}:
                        raise ValueError("Получен документ другого типа вместо HTML-статьи.")
                    entry = FeedEntry(article["url"], article["feed_title"], article["feed_published_at"])
                    extracted = extract_article(response.text(), response.url, source, entry)
                    analysis = analyze(extracted["document"])
                    saved = store.save(article, extracted, response, analysis, now(), revisit_seconds)
                    result["fetched"] += 1
                    result["new_revisions"] += int(saved["new_revision"])
                    result["new_analyses"] += int(saved["new_analysis"])
                    result["unchanged"] += int(not saved["new_revision"])
                    if log:
                        log({"event": "article_saved", "source": source.id, "url": article["url"], **saved})
                except (FetchError, ValueError) as exc:
                    store.fail(article, exc, now(), getattr(exc, "retry_after", 0))
                    result["failed"] += 1
                    error = {"url": article["url"], "error": str(exc)}
                    result["errors"].append(error)
                    if log:
                        log({"event": "article_failed", "source": source.id, **error})
        except (FetchError, ValueError) as exc:
            result["errors"].append({"url": source.feed_url, "error": str(exc)})
            retry_after = getattr(exc, "retry_after", 0)
        success = result["feed_ok"] and not result["errors"]
        store.source_result(source, now(), result["feed_ok"],
                            None if success else "; ".join(dict.fromkeys(item["error"] for item in result["errors"]))[:2000],
                            retry_after)
        summary["success"] = summary["success"] and success
        summary["sources"][source.id] = result
        if log:
            log({"event": "source_finished", "source": source.id, **result})
    store.finish_run(run_id, now(), summary)
    return summary


def reextract_current(store, source_ids=None, now=utcnow):
    selected = set(source_ids or SOURCES)
    if selected - SOURCES.keys():
        raise ValueError("Допустимые источники: rt, tass, ria.")
    summary = {"success": True, "processed": 0, "new_revisions": 0, "new_analyses": 0, "errors": []}
    for article in store.retained_pages():
        if article["source_id"] not in selected:
            continue
        try:
            response = Response(article["page_url"], gzip.decompress(article["raw_html_gzip"]), article["content_type"])
            source = SOURCES[article["source_id"]]
            entry = FeedEntry(article["url"], article["feed_title"], article["feed_published_at"])
            extracted = extract_article(response.text(), response.url, source, entry)
            result = analyze(extracted["document"])
            saved = store.save(article, extracted, response, result, now(), revisit_seconds=3600,
                               retrieved_at=article["retrieved_at"], refresh_schedule=False)
            summary["processed"] += 1
            summary["new_revisions"] += int(saved["new_revision"])
            summary["new_analyses"] += int(saved["new_analysis"])
        except (FetchError, ValueError, OSError, EOFError) as exc:
            summary["success"] = False
            summary["errors"].append({"url": article["url"], "error": str(exc)})
    return summary


def reanalyze_current(store, source_ids=None, now=utcnow):
    """Add the current rules' result without altering texts or download times."""
    selected = set(source_ids or SOURCES)
    if selected - SOURCES.keys():
        raise ValueError("Допустимые источники: rt, tass, ria.")
    summary = {"success": True, "processed": 0, "new_analyses": 0, "errors": []}
    for item in store.pending_analyses():
        if item["source_id"] not in selected:
            continue
        try:
            result = analyze(item["document"])
            summary["new_analyses"] += int(store.save_analysis(item["revision_id"], result, now()))
            summary["processed"] += 1
        except ValueError as exc:
            summary["success"] = False
            summary["errors"].append({"article_id": item["article_id"], "error": str(exc)})
    return summary


def watch(database, sources=None, interval=300, limit=5, revisit_seconds=3600,
          client_factory=SourceClient, stop_event=None):
    if interval < 60:
        raise ValueError("Интервал проверки лент должен быть не меньше 60 секунд.")
    stop = stop_event if stop_event is not None else threading.Event()
    previous = {}
    def shutdown(signum, frame):
        stop.set()
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous[signum] = signal.signal(signum, shutdown)
    try:
        with collection_lock(database), Store(database) as store:
            while not stop.is_set():
                factory = (lambda source: SourceClient(source, stop_event=stop)) if client_factory is SourceClient else client_factory
                summary = collect_once(store, sources, limit, revisit_seconds, client_factory=factory,
                                       log=lambda event: print(json.dumps(event, ensure_ascii=False), flush=True),
                                       stop_event=stop)
                print(json.dumps({"event": "cycle_finished", **summary}, ensure_ascii=False), flush=True)
                stop.wait(interval)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)

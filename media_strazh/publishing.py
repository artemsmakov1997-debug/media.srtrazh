"""Bounded reports for Pages, with short Telegram previews and no corpus/database."""

import json
import re
from pathlib import Path
import shutil
import tempfile

from .analysis import VERSION, taxonomy
from .browser import DEFAULT_RUNTIME, engine_bundle, runtime_assets
from .sources import SOURCES, normalize_url, resolve_source
from .storage import utcnow

SCHEMA = "public-snapshot-1.0"
ROOT = Path(__file__).resolve().parents[1]
STATIC_SUFFIXES = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif",
                   ".webp", ".svg", ".ico", ".webmanifest", ".xml"}


def bounded_findings(findings, limit=40):
    """Keep each category visible, then fill fairly; retain source order."""
    buckets = {}
    for index, finding in enumerate(findings):
        buckets.setdefault(finding["category"], []).append(index)
    selected, rank = [], 0
    while len(selected) < min(limit, len(findings)):
        for indices in buckets.values():
            if rank < len(indices):
                selected.append(indices[rank])
                if len(selected) == limit:
                    break
        rank += 1
    return [findings[index] for index in sorted(selected)]


def telegram_display_excerpt(text: str, forwarded: bool = False) -> str:
    """One complete lead phrase for display only, never a fabricated headline.

    Forwarded attribution is not the publication title. The original document
    title remains empty for Telegram so analysis never doubles the same text.
    """
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if forwarded and lines:
        lines = lines[1:]
    for line in lines:
        if re.match(r"^(?:Forwarded from|Переслано из|Переслано от)\b", line, re.I):
            continue
        line = re.sub(r'^[^\w«„“"]+', "", line).strip()
        if len(line) < 15:
            continue
        sentence = re.search(r"^(.{20,220}?[.!?])(?=\s|$)", line)
        if sentence:
            return sentence.group(1)
        if len(line) <= 155 and not line.endswith("…"):
            return line
    return ""


def snapshot(store, limit=100):
    if not 1 <= limit <= 100:
        raise ValueError("Размер подборки должен быть от 1 до 100 публикаций.")
    store.db.execute("SAVEPOINT public_snapshot")
    try:
        status = store.status()
        status_by_id = {row["source_id"]: row for row in status["sources"]}
        sources = {source.id: resolve_source(source, status_by_id.get(source.id, {}).get("feed_url", ""))
                   for source in SOURCES.values()}
        articles = []
        # One busy outlet must not displace every smaller outlet or Telegram feed.
        # Keep the newest item from each available feed before taking its next item.
        source_ids = list(sources)
        placeholders = ",".join("?" for _ in source_ids)
        # Select identifiers before loading full analyses: an old, large local
        # corpus should not deserialize limit * source_count complete results.
        selected = list(store.db.execute("""
            SELECT id,published_at,retrieved_at FROM (
                SELECT a.id,a.source_id,r.published_at,r.retrieved_at,
                       (n.revision_id IS NOT NULL) AS analyzed,
                       (COALESCE(json_array_length(json_extract(n.result_json, '$.findings')),0) > 0)
                           AS has_findings,
                       ROW_NUMBER() OVER (PARTITION BY a.source_id ORDER BY
                           (n.revision_id IS NOT NULL) DESC,
                           (COALESCE(json_array_length(json_extract(n.result_json, '$.findings')),0) > 0) DESC,
                           COALESCE(NULLIF(r.published_at,''),r.retrieved_at) DESC,a.id DESC) AS rank
                FROM articles a JOIN revisions r ON r.id=a.current_revision_id
                LEFT JOIN analyses n ON n.revision_id=r.id AND n.algorithm_version=?
                WHERE a.source_id IN (""" + placeholders + """))
            ORDER BY has_findings DESC,analyzed DESC,rank,source_id LIMIT ?
        """, [VERSION, *source_ids, limit]))
        selected.sort(key=lambda row: (row["published_at"] or row["retrieved_at"], row["id"]),
                      reverse=True)
        for row in selected:
            item = store.article(row["id"])
            document, analysis = item["document"], item["analysis"]
            source = sources[item["source_id"]]
            preview = " ".join(document["text"].split()) if source.platform == "telegram" else ""
            if len(preview) > 160:
                preview = preview[:159].rstrip() + "…"
            findings = []
            if analysis:
                for finding in bounded_findings(analysis["findings"]):
                    findings.append({
                        key: finding[key] for key in
                        ("category", "label", "rule_id", "status", "explanation", "review_question", "evidence")
                    })
            forwarded = source.platform == "telegram" and item["extraction_method"].endswith(".forwarded")
            display_excerpt = telegram_display_excerpt(document["text"], forwarded) if source.platform == "telegram" else ""
            articles.append({
                "id": item["id"], "source_id": source.id, "source": source.name,
                "publisher_id": source.publisher, "platform": source.platform,
                "forwarded": forwarded,
                "title": document["title"], "url": normalize_url(document["url"], source),
                "display_excerpt": display_excerpt,
                "message_preview": preview,
                "published_at": document["published_at"], "retrieved_at": item["retrieved_at"],
                "algorithm_version": analysis["algorithm_version"] if analysis else None,
                "sha256": analysis["document"]["sha256"] if analysis else None,
                "summary": analysis["summary"] if analysis else None,
                "findings": findings,
                "findings_omitted": max(0, len(analysis["findings"]) - len(findings)) if analysis else 0,
            })
        analyzed = [item for item in articles if item["summary"] is not None]
        if not analyzed:
            raise ValueError("Нет публикаций с анализом текущей версии; предыдущий сайт не заменён.")
        return {
            "schema_version": SCHEMA, "generated_at": utcnow(), "algorithm_version": VERSION,
            "coverage": taxonomy(), "articles": articles,
            "totals": {"displayed": len(articles), "analyzed": len(analyzed),
                       "with_review_candidates": sum(item["summary"]["review_fragments"] > 0
                                                     for item in analyzed),
                       "review_fragments": sum(item["summary"]["review_fragments"] for item in analyzed)},
            "sources": [
                {"id": source.id, "name": source.name,
                 "publisher_id": source.publisher, "platform": source.platform,
                 "allowed_hosts": list(dict.fromkeys((source.host,) + source.allowed_hosts)),
                 "channel": source.channel,
                 "configuration_error": source.configuration_error,
                 "displayed": sum(item["source_id"] == source.id for item in articles),
                 "status": ({
                     key: status_by_id[source.id][key] for key in
                     ("last_attempt_at", "last_success_at", "last_error", "next_attempt_at")
                 } if source.id in status_by_id else None)}
                for source in sources.values()
            ],
        }
    finally:
        store.db.execute("RELEASE public_snapshot")


def build_site(store, output, limit=100, runtime_dir=DEFAULT_RUNTIME):
    """Build only public root assets and selected report fields in a generated directory."""
    destination = Path(output).resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("Используйте отдельный каталог сборки, например _site.")
    if destination.is_relative_to(ROOT):
        relative = destination.relative_to(ROOT)
        if relative.parts[0] != "_site":
            raise ValueError("Внутри репозитория используйте каталог _site.")
    assets = [path for path in ROOT.iterdir() if path.is_file() and not path.is_symlink()
              and (path.suffix.lower() in STATIC_SUFFIXES or path.name in {"CNAME", "robots.txt", "media-contacts.json"})]
    runtime = runtime_assets(runtime_dir)
    runtime_paths = {Path("vendor/pyodide") / name for name in runtime}
    allowed = {Path(path.name) for path in assets} | runtime_paths | {
        Path("data/analysis.json"), Path("data/manual-engine.json")}
    if destination.exists():
        for path in destination.rglob("*"):
            if path.is_symlink() or (not path.is_dir() and path.relative_to(destination) not in allowed):
                raise ValueError("В каталоге сборки есть посторонние файлы; используйте пустой каталог.")
    report = snapshot(store, limit)  # Validate before modifying any earlier output.
    destination.mkdir(parents=True, exist_ok=True)
    for path in assets:
        shutil.copy2(path, destination / path.name)
    runtime_destination = destination / "vendor" / "pyodide"
    runtime_destination.mkdir(parents=True, exist_ok=True)
    for name, path in runtime.items():
        shutil.copy2(path, runtime_destination / name)
    _write_json(destination / "data" / "manual-engine.json", engine_bundle())
    _write_json(destination / "data" / "analysis.json", report)
    return {"output": str(destination), "totals": report["totals"],
            "algorithm_version": report["algorithm_version"], "manual_analysis": True}


def _write_json(report_path, report):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=report_path.parent,
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(report_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

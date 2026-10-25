"""A 24-hour publication share from the full retained corpus, not the public sample."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import json

from .analysis import TAXONOMY, VERSION
from .quality import collection_quality
from .sources import SOURCES
from .storage import utcnow

SCHEMA = "rating-snapshot-1.0"
COUNTED_TYPES = frozenset(key for key, _, _ in TAXONOMY)
COUNTED_STATUSES = frozenset({"needs_review", "quoted_candidate"})


def rating_level(flagged, collected):
    """Classify the exact ratio, before any presentation rounding."""
    if not collected:
        return None
    return "green" if 4 * flagged < collected else "red" if 2 * flagged > collected else "yellow"


def publication_types(findings):
    """One publication can have several types but contributes only one vote.

    Reported/quoted candidates count by the project's operational convention.
    Negation/discussion, quotation-omission notices and informational layers do
    not establish the use of a rhetoric type and never create a flagged vote.
    """
    return sorted({finding["category"] for finding in findings
                   if finding.get("category") in COUNTED_TYPES
                   and finding.get("status") in COUNTED_STATUSES
                   and not any(e.get("context", {}).get("informational_notice")
                               for e in finding.get("evidence", []))})


def _percentage(flagged, collected, analyzed):
    return round(100 * flagged / collected, 6) if collected and analyzed == collected else None


def rating_snapshot(store, now=None):
    stamp = now or utcnow()
    try:
        end = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if end.utcoffset() is None:
            raise ValueError
        end = end.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError("Для рейтинга нужна дата с часовым поясом.") from exc
    start = end - timedelta(hours=24)
    stamp, begin = end.isoformat(), start.isoformat()
    store.db.execute("SAVEPOINT rating_snapshot")
    try:
        quality = collection_quality(store, stamp)
        health = {item["id"]: item for item in quality["sources"]}
        publishers = {}
        for source in SOURCES.values():
            publisher = source.publisher
            if publisher not in publishers:
                website = SOURCES.get(publisher)
                publishers[publisher] = {
                    "id": publisher, "name": website.name if website else source.name.removesuffix(" · Telegram"),
                    "platforms": [], "sources": [], "collected": 0, "analyzed": 0, "flagged": 0,
                    "by_type": Counter(), "series": [{"collected": 0, "analyzed": 0, "flagged": 0} for _ in range(24)],
                }
            item = publishers[publisher]
            if source.platform not in item["platforms"]:
                item["platforms"].append(source.platform)
            item["sources"].append({"id": source.id, "platform": source.platform,
                                    **{key: health[source.id][key] for key in
                                       ("state", "error", "last_text_at", "pending", "undated", "future_dated")}})

        placeholders = ",".join("?" for _ in SOURCES)
        rows = store.db.execute("""
            SELECT a.source_id,r.published_at,n.revision_id AS analyzed,
                   json_extract(n.result_json,'$.findings') AS findings_json
            FROM articles a JOIN revisions r ON r.id=a.current_revision_id
            LEFT JOIN analyses n ON n.revision_id=r.id AND n.algorithm_version=?
            WHERE a.source_id IN (""" + placeholders + """)
              AND julianday(r.published_at)>=julianday(?)-1.0/86400
              AND julianday(r.published_at)<=julianday(?)+1.0/86400
            ORDER BY r.id
        """, [VERSION, *SOURCES, begin, stamp])
        for row in rows:
            # A malformed/naive stored date must not be treated as a precise UTC
            # publication time, even if SQLite can interpret it.
            try:
                published = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
                if published.utcoffset() is None or not start < published <= end:
                    continue
            except (ValueError, TypeError):
                continue
            item = publishers[SOURCES[row["source_id"]].publisher]
            bucket = min(23, int((published - start).total_seconds() // 3600))
            analyzed = row["analyzed"] is not None
            types = publication_types(json.loads(row["findings_json"])) if analyzed else []
            flagged = bool(types)
            for target in (item, item["series"][bucket]):
                target["collected"] += 1
                target["analyzed"] += int(analyzed)
                target["flagged"] += int(flagged)
            item["by_type"].update(types)

        totals = Counter()
        for item in publishers.values():
            for key in ("collected", "analyzed", "flagged"):
                totals[key] += item[key]
            item["by_type"] = dict(item["by_type"])
            item["pending_analysis"] = item["collected"] - item["analyzed"]
            item["score_percent"] = _percentage(item["flagged"], item["collected"], item["analyzed"])
            item["level"] = rating_level(item["flagged"], item["collected"]) if item["score_percent"] is not None else None
            item["rating_state"] = "no_data" if not item["collected"] else "analysis_pending" if item["pending_analysis"] else "rated"
            # All feeds remain partial coverage of an outlet, including feeds
            # whose most recent request succeeded. There is no coverage percent.
            item["coverage_complete"] = False
            item["collection_states"] = dict(Counter(source["state"] for source in item["sources"]))
            running = Counter()
            for index, point in enumerate(item["series"]):
                running.update(point)
                point.update(start_at=(start + timedelta(hours=index)).isoformat(),
                             end_at=(start + timedelta(hours=index + 1)).isoformat(),
                             cumulative_collected=running["collected"],
                             cumulative_analyzed=running["analyzed"],
                             cumulative_flagged=running["flagged"],
                             score_percent=_percentage(running["flagged"], running["collected"], running["analyzed"]))
        items = sorted(publishers.values(), key=lambda item: (
            item["score_percent"] is None, -(item["score_percent"] or 0), -item["collected"], item["name"]))
        return {
            "schema_version": SCHEMA, "algorithm_version": VERSION, "generated_at": stamp,
            "window": {"start_at": begin, "end_at": stamp, "hours": 24,
                       "boundary": "start_exclusive_end_inclusive", "time_basis": "published_at"},
            "formula": {"numerator": "publications_with_at_least_one_rhetoric_type",
                        "denominator": "all_collected_publications_in_window", "multiplier": 100,
                        "counted_statuses": sorted(COUNTED_STATUSES), "counted_categories": sorted(COUNTED_TYPES),
                        "count_each_publication_once": True, "include_quoted_candidates": True,
                        "informational_notices_counted": False, "rounding_affects_level": False,
                        "green_below": 25, "yellow_from": 25, "yellow_through": 50, "red_above": 50},
            "chart": {"kind": "cumulative_share", "intervals": 24, "y_min": 0, "y_max": 100},
            "scope": "collected_sample", "coverage_complete": False,
            "totals": {**{key: totals[key] for key in ("collected", "analyzed", "flagged")},
                       "publishers": len(items), "rated_publishers": sum(item["level"] is not None for item in items),
                       "pending_analysis": totals["collected"] - totals["analyzed"],
                       "undated_in_retained_corpus": quality["undated"],
                       "future_dated_in_retained_corpus": quality["future_dated"]},
            "publishers": items,
        }
    finally:
        store.db.execute("RELEASE rating_snapshot")

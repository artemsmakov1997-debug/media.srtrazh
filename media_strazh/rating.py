"""A 24-hour publication share from the full retained corpus, not the public sample."""

from collections import Counter
from datetime import datetime, timedelta, timezone
import json

from .analysis import LABELS, VERSION
from .crossposts import MAX_GAP, VERSION_DEDUP, aware_date, current_publications, group_publications
from .quality import collection_quality
from .sources import SOURCES
from .storage import utcnow

SCHEMA = "rating-snapshot-1.0"
COUNTED_TYPES = frozenset(LABELS)
COUNTED_STATUSES = frozenset({"needs_review", "quoted_candidate", "context_only"})


def rating_level(flagged, collected):
    """Classify the exact ratio, before any presentation rounding."""
    if not collected:
        return None
    return "green" if 4 * flagged < collected else "red" if 2 * flagged > collected else "yellow"


def publication_types(findings):
    """One publication can have several types but contributes only one vote.

    All detected markers count by the project's operational convention, including
    terminology, quotation omissions, denial and discussion. Their status and
    explanation remain intact; inclusion does not establish manipulation.
    """
    return sorted({finding["category"] for finding in findings
                   if finding.get("category") in COUNTED_TYPES
                   and finding.get("status") in COUNTED_STATUSES})


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
                    "raw_publications": 0, "duplicates_excluded": 0,
                    "by_type": Counter(), "series": [{"collected": 0, "analyzed": 0, "flagged": 0} for _ in range(24)],
                }
            item = publishers[publisher]
            if source.platform not in item["platforms"]:
                item["platforms"].append(source.platform)
            item["sources"].append({"id": source.id, "platform": source.platform,
                                    **{key: health[source.id][key] for key in
                                       ("state", "error", "last_text_at", "pending", "undated", "future_dated")}})

        # Look behind the window so a newly posted copy cannot give an old
        # publication another vote. Never inspect versions dated after end.
        rows = current_publications(store, start - MAX_GAP, end, findings=True)
        rows = [row for row in rows if (date := aware_date(row["published_at"])) is not None and date <= end]
        for row in rows:
            if start < aware_date(row["published_at"]) <= end:
                publishers[SOURCES[row["source_id"]].publisher]["raw_publications"] += 1
        for group in group_publications(rows):
            published = group.published_at
            if published is None or not start < published <= end:
                continue
            item = publishers[SOURCES[group.members[0]["source_id"]].publisher]
            bucket = min(23, int((published - start).total_seconds() // 3600))
            analyzed = all(row["analyzed"] for row in group.members)
            types = sorted({kind for row in group.members if row["analyzed"]
                            for kind in publication_types(json.loads(row["findings_json"]))})
            flagged = bool(types)
            for target in (item, item["series"][bucket]):
                target["collected"] += 1
                target["analyzed"] += int(analyzed)
                target["flagged"] += int(flagged)
            item["by_type"].update(types)

        totals = Counter()
        for item in publishers.values():
            item["duplicates_excluded"] = item["raw_publications"] - item["collected"]
            for key in ("collected", "analyzed", "flagged", "raw_publications", "duplicates_excluded"):
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
            "formula": {"numerator": "publications_with_at_least_one_marker",
                        "denominator": "all_collected_publications_in_window", "multiplier": 100,
                        "counted_statuses": sorted(COUNTED_STATUSES), "counted_categories": sorted(COUNTED_TYPES),
                        "count_each_publication_once": True, "include_quoted_candidates": True,
                        "marker_weight": 1, "context_only_counted": True,
                        "informational_notices_counted": True, "rounding_affects_level": False,
                        "cross_platform_duplicates_count_once": True,
                        "duplicate_time_basis": "earliest_publication", "duplicate_marker_types": "union_of_variants",
                        "green_below": 25, "yellow_from": 25, "yellow_through": 50, "red_above": 50},
            "deduplication": {"version": VERSION_DEDUP, "scope": "same_publisher_cross_platform",
                              "max_gap_hours": int(MAX_GAP.total_seconds() / 3600), "originals_retained": True},
            "chart": {"kind": "cumulative_share", "intervals": 24, "y_min": 0, "y_max": 100},
            "scope": "collected_sample", "coverage_complete": False,
            "totals": {**{key: totals[key] for key in ("collected", "analyzed", "flagged", "raw_publications", "duplicates_excluded")},
                       "publishers": len(items), "rated_publishers": sum(item["level"] is not None for item in items),
                       "pending_analysis": totals["collected"] - totals["analyzed"],
                       "undated_in_retained_corpus": quality["undated"],
                       "future_dated_in_retained_corpus": quality["future_dated"]},
            "publishers": items,
        }
    finally:
        store.db.execute("RELEASE rating_snapshot")

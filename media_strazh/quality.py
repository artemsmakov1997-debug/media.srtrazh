"""Observable collection health, not a claim of complete publisher coverage."""

from collections import Counter
from datetime import datetime, timezone

from .sources import SOURCES


def collection_quality(store, now=None):
    stamp = now or datetime.now(timezone.utc).isoformat()
    status = {r["source_id"]: dict(r) for r in store.db.execute("SELECT * FROM source_status")}
    rows = {r["source_id"]: dict(r) for r in store.db.execute("""
        SELECT a.source_id,COUNT(*) AS discovered,
          SUM(a.current_revision_id IS NULL) AS pending,
          SUM(a.current_revision_id IS NOT NULL) AS collected,
          SUM(a.current_revision_id IS NOT NULL AND julianday(r.published_at) IS NULL) AS undated,
          SUM(julianday(r.published_at)>julianday(?)) AS future_dated,
          SUM(julianday(r.published_at)>julianday(?)-1 AND julianday(r.published_at)<=julianday(?)) AS collected_24h,
          MAX(a.last_fetched_at) AS last_text_at
        FROM articles a LEFT JOIN revisions r ON r.id=a.current_revision_id GROUP BY a.source_id
    """, (stamp, stamp, stamp))}
    sources = []
    for source in SOURCES.values():
        metrics = rows.get(source.id, {})
        saved = status.get(source.id, {})
        error = saved.get("last_error") or source.configuration_error
        last_text = metrics.get("last_text_at")
        recent = False
        if last_text:
            recent = 0 <= (datetime.fromisoformat(stamp) - datetime.fromisoformat(last_text)).total_seconds() <= 7200
        state = "partial" if error and recent else "error" if error else "stale" if saved and not recent else "pending" if not saved else "current"
        sources.append({"id": source.id, "state": state, "error": error,
                        "last_text_at": last_text,
                        **{key: int(metrics.get(key) or 0) for key in
                           ("discovered", "pending", "collected", "undated", "future_dated", "collected_24h")}})
    return {"as_of": stamp, "scope": "collected_sample", "complete": False,
            "sources": sources, "states": dict(Counter(s["state"] for s in sources)),
            "collected": sum(s["collected"] for s in sources),
            "undated": sum(s["undated"] for s in sources),
            "future_dated": sum(s["future_dated"] for s in sources),
            "pending": sum(s["pending"] for s in sources)}

"""Durable discovery, immutable article versions and versioned analysis in SQLite."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sqlite3

from .analysis import SUPPORTED, VERSION

DEFAULT_DB = Path("data/media-strazh.sqlite3")
SCHEMA_VERSION = 1


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def later(value, seconds):
    return (datetime.fromisoformat(value) + timedelta(seconds=seconds)).isoformat(timespec="microseconds")


@contextmanager
def collection_lock(database):
    # The worker is intended for Linux. Readers can use the DB while it runs.
    import fcntl
    path = Path(database)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.with_name(path.name + ".collector.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Для этой базы уже запущен сборщик.") from exc
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


class Store:
    def __init__(self, path=DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA busy_timeout=10000")
        self.db.execute("PRAGMA journal_mode=WAL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, SCHEMA_VERSION):
            self.db.close()
            raise ValueError("Версия базы не поддерживается этой программой.")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, url TEXT NOT NULL UNIQUE,
                feed_title TEXT NOT NULL, feed_published_at TEXT NOT NULL,
                first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL,
                last_fetched_at TEXT, next_attempt_at TEXT NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0, last_error TEXT,
                current_revision_id INTEGER REFERENCES revisions(id)
            );
            CREATE INDEX IF NOT EXISTS articles_due ON articles(source_id, next_attempt_at);
            CREATE TABLE IF NOT EXISTS revisions (
                id INTEGER PRIMARY KEY, article_id INTEGER NOT NULL REFERENCES articles(id),
                revision_key TEXT NOT NULL, content_hash TEXT NOT NULL,
                title TEXT NOT NULL, text TEXT NOT NULL, source TEXT NOT NULL,
                canonical_url TEXT NOT NULL, published_at TEXT NOT NULL, retrieved_at TEXT NOT NULL,
                extractor_version TEXT NOT NULL, extraction_method TEXT NOT NULL,
                raw_html_gzip BLOB NOT NULL, content_type TEXT NOT NULL,
                UNIQUE(article_id, revision_key)
            );
            CREATE TABLE IF NOT EXISTS analyses (
                revision_id INTEGER NOT NULL REFERENCES revisions(id), algorithm_version TEXT NOT NULL,
                created_at TEXT NOT NULL, result_json TEXT NOT NULL,
                PRIMARY KEY(revision_id, algorithm_version)
            );
            CREATE TABLE IF NOT EXISTS source_status (
                source_id TEXT PRIMARY KEY, feed_url TEXT NOT NULL,
                last_attempt_at TEXT NOT NULL, last_success_at TEXT, last_error TEXT,
                failures INTEGER NOT NULL DEFAULT 0, next_attempt_at TEXT
            );
            CREATE TABLE IF NOT EXISTS collection_runs (
                id INTEGER PRIMARY KEY, started_at TEXT NOT NULL,
                finished_at TEXT, summary_json TEXT
            );
        """)
        self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.db.commit()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.db.close()

    def discover(self, source_id, entries, now):
        inserted = 0
        with self.db:
            for entry in entries:
                cursor = self.db.execute("""
                    INSERT OR IGNORE INTO articles
                    (source_id,url,feed_title,feed_published_at,first_seen_at,last_seen_at,next_attempt_at)
                    VALUES (?,?,?,?,?,?,?)
                """, (source_id, entry.url, entry.title, entry.published_at, now, now, now))
                inserted += cursor.rowcount
                self.db.execute("""
                    UPDATE articles SET last_seen_at=?,feed_title=?,feed_published_at=? WHERE url=?
                """, (now, entry.title, entry.published_at, entry.url))
        return inserted

    def due(self, source_id, now, limit):
        # Revisit recently visible articles, without endlessly redownloading the archive.
        cutoff = later(now, -86400)
        return [dict(row) for row in self.db.execute("""
            SELECT * FROM articles WHERE source_id=? AND next_attempt_at<=?
              AND (current_revision_id IS NULL OR last_seen_at>=?)
            ORDER BY current_revision_id IS NOT NULL, next_attempt_at, id LIMIT ?
        """, (source_id, now, cutoff, limit))]

    def fail(self, article, error, now, retry_after=0):
        failures = article["failures"] + 1
        delay = max(min(300 * 2 ** min(failures - 1, 6), 3600), retry_after)
        with self.db:
            self.db.execute("""
                UPDATE articles SET failures=?,last_error=?,next_attempt_at=? WHERE id=?
            """, (failures, str(error)[:1000], later(now, delay), article["id"]))

    def save(self, article, extracted, response, analysis, now, revisit_seconds,
             retrieved_at=None, refresh_schedule=True):
        document = extracted["document"]
        key = hashlib.sha256(json.dumps(document, ensure_ascii=False, sort_keys=True,
                                       separators=(",", ":")).encode()).hexdigest()
        with self.db:
            cursor = self.db.execute("""
                INSERT OR IGNORE INTO revisions
                (article_id,revision_key,content_hash,title,text,source,canonical_url,published_at,
                 retrieved_at,extractor_version,extraction_method,raw_html_gzip,content_type)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (article["id"], key, analysis["document"]["sha256"], document["title"], document["text"],
                  document["source"], document["url"], document["published_at"], retrieved_at or now,
                  extracted["extractor_version"], extracted["extraction_method"],
                  gzip.compress(response.data, mtime=0), response.content_type))
            new_revision = cursor.rowcount == 1
            revision_id = self.db.execute("SELECT id FROM revisions WHERE article_id=? AND revision_key=?",
                                          (article["id"], key)).fetchone()[0]
            cursor = self.db.execute("""
                INSERT OR IGNORE INTO analyses (revision_id,algorithm_version,created_at,result_json)
                VALUES (?,?,?,?)
            """, (revision_id, analysis["algorithm_version"], now, json.dumps(analysis, ensure_ascii=False)))
            new_analysis = cursor.rowcount == 1
            if refresh_schedule:
                self.db.execute("""
                    UPDATE articles SET current_revision_id=?,last_fetched_at=?,next_attempt_at=?,
                        failures=0,last_error=NULL WHERE id=?
                """, (revision_id, now, later(now, revisit_seconds), article["id"]))
            else:
                self.db.execute("UPDATE articles SET current_revision_id=? WHERE id=?", (revision_id, article["id"]))
        return {"revision_id": revision_id, "new_revision": new_revision, "new_analysis": new_analysis}

    def source_retry_at(self, source, now):
        row = self.db.execute("SELECT feed_url,next_attempt_at FROM source_status WHERE source_id=?",
                              (source.id,)).fetchone()
        if row and row["feed_url"] == source.feed_url and row["next_attempt_at"] and row["next_attempt_at"] > now:
            return row["next_attempt_at"]
        return None

    def retry_now(self, source_ids, now):
        with self.db:
            for source_id in source_ids:
                self.db.execute("UPDATE articles SET next_attempt_at=? WHERE source_id=? AND last_error IS NOT NULL",
                                (now, source_id))
                self.db.execute("UPDATE source_status SET next_attempt_at=? WHERE source_id=?", (now, source_id))

    def source_result(self, source, now, success, error=None, retry_after=0):
        old = self.db.execute("SELECT failures FROM source_status WHERE source_id=?", (source.id,)).fetchone()
        failures = 0 if success else (old[0] if old else 0) + 1
        delay = max(min(300 * 2 ** min(max(failures - 1, 0), 6), 3600), retry_after)
        with self.db:
            self.db.execute("""
                INSERT INTO source_status
                    (source_id,feed_url,last_attempt_at,last_success_at,last_error,failures,next_attempt_at)
                VALUES (?,?,?,?,?,?,?) ON CONFLICT(source_id) DO UPDATE SET
                    feed_url=excluded.feed_url,last_attempt_at=excluded.last_attempt_at,
                    last_success_at=COALESCE(excluded.last_success_at,source_status.last_success_at),
                    last_error=excluded.last_error,failures=excluded.failures,next_attempt_at=excluded.next_attempt_at
            """, (source.id, source.feed_url, now, now if success else None, error, failures,
                  None if success else later(now, delay)))

    def start_run(self, now):
        with self.db:
            return self.db.execute("INSERT INTO collection_runs (started_at) VALUES (?)", (now,)).lastrowid

    def finish_run(self, run_id, now, summary):
        with self.db:
            self.db.execute("UPDATE collection_runs SET finished_at=?,summary_json=? WHERE id=?",
                            (now, json.dumps(summary, ensure_ascii=False), run_id))

    def status(self):
        last = self.db.execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1").fetchone()
        return {
            "articles_discovered": self.db.execute("SELECT COUNT(*) FROM articles").fetchone()[0],
            "articles_collected": self.db.execute("SELECT COUNT(*) FROM articles WHERE current_revision_id IS NOT NULL").fetchone()[0],
            "revisions": self.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0],
            "analyses": self.db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0],
            "pending": self.db.execute("SELECT COUNT(*) FROM articles WHERE current_revision_id IS NULL").fetchone()[0],
            "sources": [dict(row) for row in self.db.execute("SELECT * FROM source_status ORDER BY source_id")],
            "last_run": ({"id": last["id"], "started_at": last["started_at"], "finished_at": last["finished_at"],
                          "summary": json.loads(last["summary_json"]) if last["summary_json"] else None} if last else None),
        }

    def articles(self, source_id=None, limit=25, offset=0):
        where = " AND a.source_id=?" if source_id else ""
        params = [VERSION]
        if source_id:
            params.append(source_id)
        params.extend([limit, offset])
        rows = self.db.execute("""
            SELECT a.id,a.source_id,a.last_fetched_at,a.last_error,
                   r.id AS revision_id,r.title,r.canonical_url AS url,r.published_at,r.retrieved_at,
                   n.result_json FROM articles a JOIN revisions r ON r.id=a.current_revision_id
                   LEFT JOIN analyses n ON n.revision_id=r.id AND n.algorithm_version=?
            WHERE 1=1
        """ + where + " ORDER BY COALESCE(NULLIF(r.published_at,''),r.retrieved_at) DESC,a.id DESC LIMIT ? OFFSET ?", params)
        items = []
        for row in rows:
            item = dict(row)
            result = json.loads(item.pop("result_json")) if row["result_json"] else None
            item["analysis_summary"] = result["summary"] if result else None
            item["algorithm_version"] = result["algorithm_version"] if result else None
            items.append(item)
        return items

    def article(self, article_id):
        row = self.db.execute("""
            SELECT a.source_id,a.last_fetched_at,a.last_error,r.id AS revision_id,
                   r.title,r.text,r.source,r.canonical_url,r.published_at,r.retrieved_at,
                   r.extractor_version,r.extraction_method,n.result_json FROM articles a
            JOIN revisions r ON r.id=a.current_revision_id
            LEFT JOIN analyses n ON n.revision_id=r.id AND n.algorithm_version=? WHERE a.id=?
        """, (VERSION, article_id)).fetchone()
        if row is None:
            return None
        return {"id": article_id, "source_id": row["source_id"], "revision_id": row["revision_id"],
                "last_fetched_at": row["last_fetched_at"], "last_error": row["last_error"],
                "retrieved_at": row["retrieved_at"], "extractor_version": row["extractor_version"],
                "extraction_method": row["extraction_method"],
                "analysis": json.loads(row["result_json"]) if row["result_json"] else None,
                "document": {"title": row["title"], "text": row["text"], "source": row["source"],
                             "url": row["canonical_url"], "published_at": row["published_at"]}}

    def export_corpus(self):
        for row in self.db.execute("""
            SELECT a.id,a.source_id,r.id AS revision_id,r.title,r.text,r.source,r.canonical_url,
                   r.published_at,r.retrieved_at,r.content_hash,r.extractor_version
            FROM articles a JOIN revisions r ON r.id=a.current_revision_id ORDER BY a.id
        """):
            yield {"id": f"{row['source_id']}:{row['id']}:r{row['revision_id']}",
                   "fully_annotated": False, "labels": None,
                   "annotation_categories": sorted(SUPPORTED),
                   "document": {"title": row["title"], "text": row["text"], "source": row["source"],
                                "url": row["canonical_url"], "published_at": row["published_at"]},
                   "provenance": {"retrieved_at": row["retrieved_at"], "sha256": row["content_hash"],
                                  "extractor_version": row["extractor_version"]}}

    def pending_analyses(self):
        for row in self.db.execute("""
            SELECT a.id,a.source_id,r.id AS revision_id,r.title,r.text,r.source,r.canonical_url,r.published_at
            FROM articles a JOIN revisions r ON r.id=a.current_revision_id
            LEFT JOIN analyses n ON n.revision_id=r.id AND n.algorithm_version=?
            WHERE n.revision_id IS NULL ORDER BY a.id
        """, (VERSION,)):
            yield {"article_id": row["id"], "source_id": row["source_id"], "revision_id": row["revision_id"],
                   "document": {"title": row["title"], "text": row["text"], "source": row["source"],
                                "url": row["canonical_url"], "published_at": row["published_at"]}}

    def save_analysis(self, revision_id, analysis, now):
        with self.db:
            cursor = self.db.execute("""
                INSERT OR IGNORE INTO analyses (revision_id,algorithm_version,created_at,result_json)
                VALUES (?,?,?,?)
            """, (revision_id, analysis["algorithm_version"], now, json.dumps(analysis, ensure_ascii=False)))
        return cursor.rowcount == 1

    def retained_pages(self):
        for row in self.db.execute("""
            SELECT a.*,r.raw_html_gzip,r.content_type,r.retrieved_at,r.canonical_url AS page_url
            FROM articles a JOIN revisions r ON r.id=a.current_revision_id ORDER BY a.id
        """):
            yield dict(row)

"""Small runtime stand-ins for publication unit tests; browser checks use real Wasm."""

import hashlib
import json
from pathlib import Path

from media_strazh.browser import MANIFEST, RUNTIME_FILES, RUNTIME_INTEGRITY, RUNTIME_VERSION


def runtime_fixture(directory):
    directory = Path(directory)
    directory.mkdir(parents=True)
    hashes = {}
    for name in RUNTIME_FILES:
        data = ("unit-test fixture: " + name).encode()
        (directory / name).write_bytes(data)
        hashes[name] = hashlib.sha256(data).hexdigest()
    (directory / MANIFEST).write_text(json.dumps({
        "version": RUNTIME_VERSION, "archive_sha512": RUNTIME_INTEGRITY, "files": hashes,
    }))
    return directory
def business_evidence_fixture():
    """Synthetic dated corpus for UI tests, generated through the real publisher."""
    from datetime import datetime, timedelta, timezone
    import tempfile
    from media_strazh.analysis import analyze
    from media_strazh.business import business_snapshot
    from media_strazh.extraction import FeedEntry
    from media_strazh.network import Response
    from media_strazh.sources import SOURCES
    from media_strazh.storage import Store

    end = datetime.now(timezone.utc)
    stamp = end.isoformat()
    source = SOURCES["ria"]
    text = ('Компании «Тестовая компания», «Тест» и «Медтест» обсуждали отраслевые темы. '
            'Медицинское оборудование для клиник, регистрация медизделий и диагностика. '
            'Промышленность, логистика, автоматизация и инженеры. '
            'Гостиницы, туристы, рестораны и гостиничный сервис.')
    with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "evidence.sqlite3") as store:
        for number, days_ago in enumerate((1, 4, 11, 18, 38, 68), 1):
            date = (end - timedelta(days=days_ago)).isoformat()
            url = f"https://ria.ru/fixture/business/{number}"
            store.discover(source.id, [FeedEntry(url, "Проверочная публикация " + str(number), date)], stamp)
            row = store.due(source.id, stamp, 100)[0]
            document = {"title": "Проверочная публикация " + str(number), "text": text,
                        "source": source.name, "url": url, "published_at": date}
            store.save(row, {"document": document, "extractor_version": "fixture", "extraction_method": "fixture"},
                       Response(url, b"fixture", "text/html"), analyze(document), stamp, 3600)
        store.db.execute("UPDATE articles SET first_seen_at=?", ((end - timedelta(days=200)).isoformat(),))
        store.db.execute("UPDATE revisions SET retrieved_at=?", ((end - timedelta(days=200)).isoformat(),))
        return business_snapshot(store, stamp)

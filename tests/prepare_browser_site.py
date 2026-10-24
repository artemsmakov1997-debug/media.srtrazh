"""Build the actual public site from a small synthetic corpus, without network collection."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_strazh.analysis import analyze
from media_strazh.browser import DEFAULT_RUNTIME
from media_strazh.extraction import FeedEntry
from media_strazh.network import Response
from media_strazh.publishing import build_site
from media_strazh.sources import SOURCES
from media_strazh.storage import Store


def prepare(output, runtime):
    now = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory() as directory, Store(Path(directory)/'fixture.sqlite3') as store:
        cases = [('rt', 'website'), ('rt', 'telegram'), ('mediazona', 'telegram'),
                 ('meduza', 'website'), ('tass', 'telegram')]
        for number, (publisher, platform) in enumerate(cases, 1):
            source = next(s for s in SOURCES.values() if s.publisher == publisher and s.platform == platform)
            path = f'/{source.channel}/{number}' if platform == 'telegram' else f'/fixture/analysis/{number}'
            url = f'https://{source.host}{path}'
            published = '2026-10-23T20:44:27+00:00' if number != 5 else ''
            document = {'title': '' if platform == 'telegram' else f'Проверочная публикация {number}',
                        'text': 'Все знают: нас ждёт неминуемая катастрофа. Это проверочный текст интерфейса.',
                        'source': source.name, 'url': url, 'published_at': published}
            if number == 4:
                document['source'] = 'Проверочное очень длинное название редакции для переноса строк'
            store.discover(source.id, [FeedEntry(url, document['title'], published)], now)
            row = next(row for row in store.due(source.id, now, 100) if row['url'] == url)
            store.save(row, {'document': document, 'extractor_version': 'fixture', 'extraction_method': 'fixture'},
                       Response(url, b'fixture', 'text/html'), analyze(document), now, 3600)
        build_site(store, output, runtime_dir=runtime)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    args = parser.parse_args()
    prepare(args.output, args.runtime)

"""Synthetic checks of coverage, dates and fair queues, not a news benchmark."""
import json
from pathlib import Path
import tempfile
import unittest

from media_strazh.analysis import analyze
from media_strazh.collector import collect_once
from media_strazh.extraction import FeedEntry, extract_article, parse_feed
from media_strazh.quality import collection_quality
from media_strazh.sources import SOURCES, normalize_url
from media_strazh.storage import Store
from test_collector import BODY, NOW, FakeNetwork, page


class CollectionQualityTests(unittest.TestCase):
    def test_canonical_publisher_aliases_do_not_need_cross_host_robots_redirects(self):
        self.assertEqual(normalize_url('https://russian.rt.com/news/1', SOURCES['rt']), 'https://russiatoday.ru/news/1')
        self.assertEqual(normalize_url('https://fontanka.ru/news/1', SOURCES['fontanka']), 'https://www.fontanka.ru/news/1')
        self.assertEqual(SOURCES['rt'].feed_url, 'https://russiatoday.ru/rss')
        for url in ('https://russian.rt.com.evil.example/1', 'https://user:secret@russiatoday.ru/1'):
            with self.assertRaises(ValueError): normalize_url(url, SOURCES['rt'])

    def test_explicit_publication_dates_without_article_body_in_jsonld(self):
        for payload in ({'@type':'NewsArticle','datePublished':'2026-10-10T12:00:00+03:00'},
                        {'@type':'Article','@id':'https://ria.ru/news/1#article','datePublished':'2026-10-10T12:00:00+03:00'}):
            html='<script type="application/ld+json">'+json.dumps(payload)+'</script><div class="article__text">'+BODY+'</div>'
            result=extract_article(html,'https://ria.ru/news/1',SOURCES['ria'],FeedEntry('https://ria.ru/news/1','Новость'))
            self.assertEqual(result['document']['published_at'],'2026-10-10T09:00:00+00:00')

    def test_microdata_and_meta_publication_dates_exclude_modification_and_sidebar(self):
        wrappers=(('<time itemprop="datePublished" datetime="2026-10-10T12:00:00+03:00"></time>',True),
                  ('<meta itemprop="datePublished" content="2026-10-10T12:00:00+03:00">',True),
                  ('<meta name="parsely-pub-date" content="2026-10-10T12:00:00+03:00">',True),
                  ('<time itemprop="dateModified" datetime="2026-10-10T12:00:00+03:00"></time>',False),
                  ('<aside><meta itemprop="datePublished" content="2026-10-10T12:00:00+03:00"></aside>',False),
                  ('<time itemprop="datePublished" datetime="2026-10-10T12:00:00"></time>',False))
        for markup,expected in wrappers:
            with self.subTest(markup=markup):
                html=markup+'<div class="article__text">'+BODY+'</div>'
                doc=extract_article(html,'https://ria.ru/news/1',SOURCES['ria'],FeedEntry('https://ria.ru/news/1','Новость'))['document']
                self.assertEqual(bool(doc['published_at']),expected)

    def test_atom_updated_is_not_used_as_publication_date(self):
        feed=b'<feed><entry><title>News</title><link href="https://ria.ru/news/1"/><updated>2026-10-11T12:00:00Z</updated><published>2026-10-10T12:00:00Z</published></entry></feed>'
        self.assertEqual(parse_feed(feed,SOURCES['ria'])[0].published_at,'2026-10-10T12:00:00+00:00')
        self.assertEqual(parse_feed(feed.replace(b'<published>2026-10-10T12:00:00Z</published>',b''),SOURCES['ria'])[0].published_at,'')

    def test_conflicting_publication_microdata_stays_unknown(self):
        html=''.join('<time itemprop="datePublished" datetime="'+date+'"></time>' for date in ('2026-10-10T12:00:00Z','2026-10-11T12:00:00Z'))+'<div class="article__text">'+BODY+'</div>'
        doc=extract_article(html,'https://ria.ru/news/1',SOURCES['ria'],FeedEntry('https://ria.ru/news/1','Новость'))['document']
        self.assertEqual(doc['published_at'],'')

    def test_newest_unseen_news_and_old_backlog_both_get_a_slot(self):
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory)/'queue.sqlite3') as store:
            store.discover('ria',[FeedEntry('https://ria.ru/old','Старая','2026-10-01T09:00:00+00:00')],'2026-10-01T09:00:00+00:00')
            store.discover('ria',[FeedEntry('https://ria.ru/new1','Новая','2026-10-10T08:00:00+00:00'),FeedEntry('https://ria.ru/new2','Свежая','2026-10-10T09:00:00+00:00')],NOW)
            result=store.due('ria',NOW,2)
            self.assertEqual([r['url'] for r in result],['https://ria.ru/new2','https://ria.ru/old'])
            store.fail(result[0],ValueError('temporary'),NOW)
            self.assertNotIn(result[0]['id'],[r['id'] for r in store.due('ria',NOW,2)])

    def test_quality_distinguishes_partial_stale_and_never_checked_sources(self):
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory)/'health.sqlite3') as store:
            collect_once(store,[SOURCES['ria']],client_factory=FakeNetwork(),now=lambda:NOW,limit=1)
            store.source_result(SOURCES['ria'],NOW,False,'Один текст недоступен')
            q=collection_quality(store,NOW); by_id={r['id']:r for r in q['sources']}
            self.assertEqual(by_id['ria']['state'],'partial')
            self.assertEqual(by_id['tass']['state'],'pending')
            self.assertFalse(q['complete'])
            self.assertEqual(q['scope'],'collected_sample')
            self.assertEqual(by_id['ria']['undated'],0)
            store.source_result(SOURCES['ria'],NOW,True)
            later=collection_quality(store,'2026-10-20T09:00:00+00:00')
            self.assertEqual(next(r for r in later['sources'] if r['id']=='ria')['state'],'stale')

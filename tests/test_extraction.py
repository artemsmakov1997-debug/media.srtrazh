import json
import unittest

from media_strazh.extraction import FeedEntry, extract_article, parse_feed, timestamp
from media_strazh.sources import SOURCES, normalize_url

# Synthetic fixtures for program behavior, not real news or a quality corpus.
TEXT = ("Городская библиотека открыла новый читальный зал. Жители смогут пользоваться "
        "книгами и электронным каталогом. Расписание работы опубликовано на сайте учреждения.")


class FeedTests(unittest.TestCase):
    def test_rss_dates_cdata_and_tracking_duplicates(self):
        data = b'''<rss><channel><item><title><![CDATA[Title &amp; text]]></title>
          <link>https://tass.ru/test/1?utm_source=a</link><pubDate>Sat, 10 Oct 2026 09:05:00 GMT</pubDate>
          <description>Not a full article</description></item><item><title>Duplicate</title>
          <link>https://tass.ru/test/1#fragment</link></item></channel></rss>'''
        entries = parse_feed(data, SOURCES["tass"])
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].url, "https://tass.ru/test/1")
        self.assertEqual(entries[0].title, "Title & text")
        self.assertEqual(entries[0].published_at, "2026-10-10T09:05:00+00:00")
        self.assertFalse(hasattr(entries[0], "text"))

    def test_atom_relative_links_and_namespace(self):
        data = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Title</title>
          <link rel="self" href="/wrong"/><link rel="alternate" href="/20261010/article.html"/>
          <published>2026-10-10T12:00:00+03:00</published></entry></feed>'''
        entry = parse_feed(data, SOURCES["ria"])[0]
        self.assertEqual(entry.url, "https://ria.ru/20261010/article.html")
        self.assertEqual(entry.published_at, "2026-10-10T09:00:00+00:00")

    def test_invalid_feed_and_external_links(self):
        fixtures = [b'<html>Denied</html>', b'<rss>',
                    b'<rss><channel><item><title>Title</title><link>https://example.org/1</link></item></channel></rss>',
                    b'<!DOCTYPE rss [<!ENTITY x "expansion">]><rss><channel/></rss>']
        for data in fixtures:
            with self.subTest(data=data):
                with self.assertRaises(ValueError):
                    parse_feed(data, SOURCES["rt"])

    def test_url_scope_and_normalization(self):
        self.assertEqual(normalize_url("http://ria.ru/1?b=2&utm_source=x&a=1#top", SOURCES["ria"]),
                         "https://ria.ru/1?a=1&b=2")
        for url in ["https://ria.ru.evil.example/1", "https://user:password@ria.ru/1",
                    "http://127.0.0.1/", "https://ria.ru:444/1", "file:///tmp/article", "https://tass.ru/1"]:
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    normalize_url(url, SOURCES["ria"])

    def test_dates_without_timezone_are_not_guessed(self):
        self.assertEqual(timestamp("2026-10-10T12:00:00"), "")
        self.assertEqual(timestamp("invalid"), "")


class ExtractionTests(unittest.TestCase):
    def extract(self, source_id, html):
        source = SOURCES[source_id]
        url = f"https://{source.host}/news/1"
        return extract_article(html, url, source, FeedEntry(url, "Заголовок ленты"))

    def test_jsonld_graph_uses_article_body_and_metadata(self):
        data = {"@graph": [{"@type": "Organization", "name": "Publisher"},
                           {"@type": "NewsArticle", "headline": "Открытие библиотеки", "articleBody": TEXT,
                            "datePublished": "2026-10-10T12:00:00+03:00", "url": "https://tass.ru/news/1"}]}
        html = '<nav>Other news</nav><script type="application/ld+json">' + json.dumps(data, ensure_ascii=False) + '</script>'
        result = self.extract("tass", html)
        self.assertEqual(result["document"]["text"], TEXT)
        self.assertEqual(result["document"]["title"], "Открытие библиотеки")
        self.assertEqual(result["document"]["published_at"], "2026-10-10T09:00:00+00:00")
        self.assertEqual(result["extraction_method"], "jsonld.articleBody")

    def test_all_publishers_body_adapters_exclude_noise(self):
        selectors = {"rt": "article__text", "tass": "text-block", "ria": "article__text"}
        for source_id, selector in selectors.items():
            with self.subTest(source=source_id):
                html = f'<meta property="og:title" content="Заголовок"><nav>Навигация</nav><div class="{selector}"><p>{TEXT}</p><div class="related-news">Не включать рекомендации</div><script>Не включать код</script></div>'
                result = self.extract(source_id, html)
                self.assertEqual(result["document"]["text"], TEXT)
                self.assertEqual(result["document"]["title"], "Заголовок")

    def test_multiple_ria_blocks_and_nested_rt_container(self):
        ria = self.extract("ria", f'<h1>Заголовок</h1><div class="article__text">{TEXT}</div><div class="article__text">Дополнительный абзац.</div>')
        self.assertEqual(ria["document"]["text"], TEXT + "\nДополнительный абзац.")
        rt = self.extract("rt", f'<div class="article__text"><div class="article__text"><p>{TEXT}</p></div></div>')
        self.assertEqual(rt["document"]["text"], TEXT)

    def test_canonical_url_must_belong_to_source(self):
        result = self.extract("rt", f'<link rel="canonical" href="https://example.org/wrong"><div class="article__text">{TEXT}</div>')
        self.assertEqual(result["document"]["url"], "https://russian.rt.com/news/1")

    def test_recommendation_jsonld_is_not_used_as_main_article(self):
        data = {"@type": "NewsArticle", "url": "https://ria.ru/news/other", "articleBody": TEXT}
        html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        with self.assertRaises(ValueError):
            self.extract("ria", html)

    def test_ambiguous_unlocated_jsonld_rejected(self):
        data = [{"@type": "NewsArticle", "articleBody": TEXT}, {"@type": "NewsArticle", "articleBody": TEXT + " Ещё текст."}]
        with self.assertRaises(ValueError):
            self.extract("tass", '<script type="application/ld+json">' + json.dumps(data) + '</script>')

    def test_preview_or_whole_page_fallback_is_rejected(self):
        for html in [f'<body><nav>{TEXT}</nav></body>', '<div class="article__text">Короткое описание</div>']:
            with self.subTest(html=html):
                with self.assertRaises(ValueError):
                    self.extract("ria", html)

    def test_malformed_jsonld_can_use_publisher_body(self):
        result = self.extract("ria", '<script type="application/ld+json">{bad</script>' + f'<div class="article__text">{TEXT}</div>')
        self.assertEqual(result["extraction_method"], "html.publisher_body")

    def test_rt_standfirst_is_included_but_not_duplicated(self):
        lead = "Вводный абзац с описанием события."
        result = self.extract("rt", f'<div class="article__summary">{lead}</div><div class="article__text">{TEXT}</div>')
        self.assertEqual(result["document"]["text"], lead + "\n" + TEXT)
        result = self.extract("rt", f'<div class="article__summary">{lead}</div><div class="article__text"><p>{lead}</p><p>{TEXT}</p></div>')
        self.assertEqual(result["document"]["text"], lead + "\n" + TEXT)

    def test_ria_ai_summary_is_not_part_of_authored_article(self):
        result = self.extract("ria", f'<div class="article__summary">Краткий пересказ от РИА ИИ. Все знают.</div><div class="article__text">{TEXT}</div>')
        self.assertEqual(result["document"]["text"], TEXT)

    def test_rt_read_more_does_not_inject_another_article_into_analysis(self):
        html = f'<div class="article__text"><p>{TEXT}</p><div class="article__read-more read-more"><h2>Также по теме</h2><p>Все знают: неминуемая катастрофа.</p></div><blockquote>Политики опасны без смирительной рубашки.</blockquote></div>'
        result = self.extract("rt", html)
        self.assertNotIn("Также по теме", result["document"]["text"])
        self.assertNotIn("неминуемая катастрофа", result["document"]["text"])
        self.assertIn("Политики опасны без смирительной рубашки", result["document"]["text"])

    def test_jsonld_metadata_without_body_has_an_aware_date(self):
        data = {"@type": "Article", "mainEntityOfPage": {"@id": "https://russian.rt.com/news/1"},
                "headline": "Колонка", "datePublished": "2026-10-08T11:24:30+03:00"}
        html = '<script type="application/ld+json">' + json.dumps(data) + f'</script><div class="article__text">{TEXT}</div>'
        result = self.extract("rt", html)
        self.assertEqual(result["document"]["published_at"], "2026-10-08T08:24:30+00:00")
        self.assertEqual(result["document"]["title"], "Колонка")

    def test_other_article_metadata_cannot_replace_current_title_or_date(self):
        data = {"@type": "Article", "url": "https://russian.rt.com/news/other",
                "headline": "Другая статья", "datePublished": "2026-10-08T11:24:30+03:00"}
        html = '<script type="application/ld+json">' + json.dumps(data) + f'</script><h1>Основная статья</h1><div class="article__text">{TEXT}</div>'
        result = self.extract("rt", html)
        self.assertEqual(result["document"]["title"], "Основная статья")
        self.assertEqual(result["document"]["published_at"], "")


if __name__ == "__main__":
    unittest.main()

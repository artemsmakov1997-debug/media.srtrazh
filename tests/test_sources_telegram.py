from dataclasses import replace
from html import escape
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from media_strazh.collector import collect_once, reextract_current, selected_sources
from media_strazh.extraction import FeedEntry, extract_article, parse_feed
from media_strazh.network import FetchError, PublisherRedirects, Response, SourceClient
from media_strazh.sources import PUBLISHERS, SOURCES, channel_from_homepage, normalize_url, resolve_source
from media_strazh.storage import Store
from media_strazh.telegram import extract_post, parse_preview
from media_strazh.analysis import analyze
from test_contextual_rhetoric import BLAHA_TEXT


NOW = "2026-10-11T10:00:00+00:00"
BODY = "Городская библиотека открыла новый читальный зал. Жители смогут пользоваться книгами и электронным каталогом. Расписание работы опубликовано на сайте учреждения."


def telegram_post(post_id, body="Новость: открыта библиотека.", channel="rt_russian", forwarded=""):
    return (f'<div class="tgme_widget_message js-widget_message" data-post="{channel}/{post_id}">'
            f'<div class="tgme_widget_message_forwarded_from">{forwarded}</div>'
            f'<div class="tgme_widget_message_text js-message_text">{body}</div>'
            '<a class="tgme_widget_message_link_preview">Все знают: ужас и катастрофа — чужая карточка</a>'
            '<span class="tgme_widget_message_views">100 000</span>'
            '<a class="tgme_widget_message_date"><time datetime="2026-10-11T12:00:00+03:00">12:00</time></a></div>')


class ExpandedSourceTests(unittest.TestCase):
    def test_user_post_retains_omission_and_quoted_signals_through_collection(self):
        source = SOURCES["izvestia_telegram"]
        html = telegram_post(253503, escape(BLAHA_TEXT).replace("\n", "<br>"), channel="izvestia")
        class Client:
            robots_error = None
            def __init__(self, selected): self.source = selected
            def get_feed(self): return Response(source.feed_url, html.encode(), "text/html", "utf-8")
            def get(self, url): raise AssertionError("Feed already includes the requested message.")
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "corpus.sqlite3") as store:
            summary = collect_once(store, [source], client_factory=Client, now=lambda: NOW)
            self.assertTrue(summary["success"])
            item = store.article(store.articles()[0]["id"])
            # The HTML adapter collapses empty paragraphs before analysis;
            # evidence offsets must refer to this stored extracted version.
            self.assertEqual(item["document"]["text"], BLAHA_TEXT.replace("\n\n", "\n"))
            self.assertEqual(item["analysis"], analyze(item["document"]))
            self.assertEqual(item["analysis"]["summary"]["candidate_fragments"], 11)
            omission = next(f for f in item["analysis"]["findings"] if f["rule_id"] == "context.quotation_omission")
            self.assertEqual(omission["evidence"][0]["quote"], "<...>")

    def test_runtime_channel_restore_uses_exact_scoped_canonical_preview(self):
        inactive = replace(SOURCES["tass_telegram"], channel="", feed_url="", configuration_error="Не подтверждён")
        resolved = resolve_source(inactive, "https://t.me/s/example_news")
        self.assertEqual((resolved.channel, resolved.publisher, resolved.configuration_error), ("example_news", "tass", ""))
        for url in ("https://evil.example/s/example_news", "https://t.me/s/example_news?before=1", "http://t.me/s/example_news", "https://t.me/other_news/1", "https://user:pass@t.me/s/example_news"):
            self.assertEqual(resolve_source(inactive, url), inactive)
        self.assertEqual(resolve_source(SOURCES["rt_telegram"], "https://t.me/s/other_news"), SOURCES["rt_telegram"])

    def test_official_homepage_channel_discovery_ignores_article_links_and_ambiguity(self):
        website = SOURCES["tass"]
        html = '<article><a href="https://t.me/unrelated_news">Ссылка в статье</a></article><footer><a href="https://t.me/example_news">Telegram</a></footer>'
        pending = replace(SOURCES["tass_telegram"], channel="", feed_url="", configuration_error="Не подтверждён")
        with patch.dict(SOURCES, {pending.id: pending}):
            self.assertEqual(channel_from_homepage(html, website).channel, "example_news")
            self.assertEqual(channel_from_homepage(html + '<footer><a href="https://t.me/feedback_bot">Сообщить редакции</a></footer>', website).channel, "example_news")
        for markup in ('<article class="article__text"><a class="social-link" href="https://t.me/unrelated_news">Чужой канал</a></article>',
                       '<footer><a href="https://t.me/first_news">A</a><a href="https://t.me/second_news">B</a></footer>',
                       '<footer><a href="https://t.me/share/url?url=test">Share</a></footer>'):
            with self.assertRaises(ValueError):
                channel_from_homepage(markup, website)

    def test_registry_covers_every_named_publisher_and_both_platforms(self):
        expected = {"rt", "tass", "ria", "interfax", "kommersant", "vedomosti", "rbc", "izvestia", "rg", "lenta", "meduza", "novayagazeta", "fontanka", "currenttime", "dw", "bbc", "aif", "inosmi"}
        self.assertEqual(set(PUBLISHERS), expected)
        self.assertEqual(len(selected_sources()), 39)
        for publisher in expected:
            self.assertEqual(SOURCES[publisher].publisher, publisher)
            self.assertEqual(SOURCES[publisher + "_telegram"].publisher, publisher)
            self.assertEqual(SOURCES[publisher + "_telegram"].platform, "telegram")

    def test_rt_first_party_rss_redirect_is_scoped_to_verified_alias(self):
        source = SOURCES["rt"]
        target = "https://russiatoday.ru/rss"
        self.assertEqual(normalize_url(target, source), target)
        redirect = PublisherRedirects(source, lambda before, after: None)
        request = redirect.redirect_request(Request(source.feed_url), None, 301, "Moved", {}, target)
        self.assertEqual(request.full_url, target)
        with self.assertRaises(FetchError):
            redirect.redirect_request(Request(source.feed_url), None, 301, "Moved", {}, "https://russiatoday.ru.evil.test/rss")
        self.assertNotIn("other", SOURCES)

    def test_user_selected_channels_and_lentach_attribution(self):
        channels = {"tass": "tass_agency", "kommersant": "kommersant", "vedomosti": "vedomosti",
                    "rbc": "rbc_news", "izvestia": "izvestia", "rg": "rgrunews", "fontanka": "fontankaspb"}
        for publisher, channel in channels.items():
            source = SOURCES[publisher + "_telegram"]
            self.assertEqual((source.channel, source.publisher, source.configuration_error), (channel, publisher, ""))
            self.assertEqual(source.feed_url, "https://t.me/s/" + channel)
        lentach = SOURCES["oldlentach_telegram"]
        self.assertEqual((lentach.channel, lentach.publisher, lentach.name), ("oldlentach", "oldlentach", "Лентач · Telegram"))
        self.assertNotEqual(lentach.publisher, SOURCES["lenta"].publisher)
        self.assertEqual(SOURCES["lenta_telegram"].channel, "")
        html = telegram_post(41, channel="oldlentach")
        entry = parse_preview(html, lentach)[0]
        self.assertEqual(extract_post(html, entry.url, lentach, entry)["document"]["source"], "Лентач · Telegram")

    def test_feed_domains_and_article_redirect_hosts_are_explicit(self):
        for source in (SOURCES[key] for key in PUBLISHERS):
            self.assertTrue(normalize_url(source.feed_url, source).startswith("https://"))
        self.assertEqual(normalize_url("https://rbc.ru/story/1", SOURCES["rbc"]), "https://rbc.ru/story/1")
        self.assertEqual(normalize_url("https://feeds.bbci.co.uk/russian/rss.xml", SOURCES["bbc"]), SOURCES["bbc"].feed_url)
        for target in ("https://news.rbc.ru/1", "https://www.dw.com.evil.example/1", "https://feeds.bbci.co.uk@127.0.0.1/1"):
            with self.assertRaises(ValueError):
                normalize_url(target, SOURCES["rbc"])

    def test_unicode_article_paths_are_percent_encoded_without_double_encoding(self):
        source = SOURCES["dw"]
        normalized = normalize_url("https://www.dw.com/ru/новость/a-123?ключ=значение", source)
        self.assertEqual(normalized, "https://www.dw.com/ru/%D0%BD%D0%BE%D0%B2%D0%BE%D1%81%D1%82%D1%8C/a-123?%D0%BA%D0%BB%D1%8E%D1%87=%D0%B7%D0%BD%D0%B0%D1%87%D0%B5%D0%BD%D0%B8%D0%B5")
        normalized.encode("ascii")
        self.assertEqual(normalize_url(normalized, source), normalized)

    def test_all_website_feeds_have_scoped_entries_and_semantic_fullbody_adapter(self):
        for key in PUBLISHERS:
            source = SOURCES[key]
            url = f"https://{source.host}/news/1"
            feed = f'<rss><channel><item><title>Новость</title><link>{url}</link></item></channel></rss>'.encode()
            entry = parse_feed(feed, source)[0]
            html = f'<h1>Библиотека</h1><div itemprop="articleBody">{BODY}</div><nav>Не основной текст</nav>'
            self.assertEqual(extract_article(html, url, source, entry)["document"]["text"], BODY)

    def test_collector_attempts_all_configured_websites(self):
        class Client:
            robots_error = None
            def __init__(self, source): self.source = source
            def get_feed(self):
                url = f"https://{self.source.host}/news/1"
                feed = f'<rss><channel><item><title>Новость</title><link>{url}</link></item></channel></rss>'
                return Response(self.source.feed_url, feed.encode(), "application/rss+xml")
            def get(self, url): return Response(url, f'<h1>Библиотека</h1><div itemprop="articleBody">{BODY}</div>'.encode(), "text/html")
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "articles.sqlite3") as store:
            summary = collect_once(store, [SOURCES[key] for key in PUBLISHERS], client_factory=Client, now=lambda: NOW)
            self.assertTrue(summary["success"])
            self.assertEqual(set(summary["sources"]), set(PUBLISHERS))
            self.assertEqual(store.status()["articles_collected"], 18)

    def test_bbc_text_blocks_are_explicit_not_wholepage(self):
        source = SOURCES["bbc"]
        url = "https://www.bbc.com/russian/articles/a1"
        html = f'<nav>Не включать</nav><div data-component="text-block"><p>{BODY}</p></div><div data-component="related-content">Не включать</div>'
        self.assertEqual(extract_article(html, url, source, FeedEntry(url, "Новость"))["document"]["text"], BODY)

    def test_bbc_public_embedded_model_matches_article_and_excludes_recommendations(self):
        source = SOURCES["bbc"]
        url = "https://www.bbc.com/russian/articles/a1"
        def block(kind, text):
            return {"type": kind, "model": {"blocks": [{"type": "paragraph", "model": {"text": text, "blocks": [{"type": "fragment", "model": {"text": text}}]}}]}}
        payload = {"props": {"pageProps": {"pageType": "article", "service": "russian", "status": 200,
                   "pathname": "/russian/articles/a1", "pageData": {"metadata": {"locators": {"canonicalUrl": url}, "firstPublished": 1791712800000},
                   "content": {"model": {"blocks": [block("headline", "Открытие библиотеки"), block("text", BODY), block("image", "Подпись к фотографии"), block("mpu", "Реклама")] }},
                   "secondaryColumn": {"blocks": [block("text", "Все знают: рекомендации.")]}}}}}
        html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
        result = extract_article(html, url, source, FeedEntry(url, "Новость"))
        self.assertEqual(result["document"]["text"], BODY)
        self.assertEqual(result["document"]["title"], "Открытие библиотеки")
        self.assertEqual(result["extraction_method"], "bbc.simorgh.article_model")
        payload["props"]["pageProps"]["pathname"] = "/russian/articles/other"
        with self.assertRaises(ValueError):
            extract_article('<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>', url, source, FeedEntry(url, ""))

    def test_bbc_malformed_embedded_types_do_not_abort_other_extraction(self):
        source = SOURCES["bbc"]
        url = "https://www.bbc.com/russian/articles/a1"
        valid_page = {"pageType": "article", "service": "russian", "status": 200,
                      "pathname": "/russian/articles/a1", "pageData": {"metadata": {"locators": {"canonicalUrl": url}},
                      "content": {"model": {"blocks": []}}}}
        fixtures = [None, [], "not an object", {"props": None}, {"props": []}]
        fixtures.extend({"props": {"pageProps": value}} for value in [None, [], "not an object"])
        for field in ("pageData",):
            for value in (None, [], "not an object"):
                page = dict(valid_page, **{field: value})
                fixtures.append({"props": {"pageProps": page}})
        for field in ("metadata", "content"):
            for value in (None, [], "not an object"):
                data = dict(valid_page["pageData"], **{field: value})
                fixtures.append({"props": {"pageProps": dict(valid_page, pageData=data)}})
        for payload in fixtures:
            html = '<script id="__NEXT_DATA__" type="application/json">' + json.dumps(payload) + '</script>'
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    extract_article(html, url, source, FeedEntry(url, ""))
                fallback = html + f'<div data-component="text-block">{BODY}</div>'
                self.assertEqual(extract_article(fallback, url, source, FeedEntry(url, ""))["document"]["text"], BODY)

    def test_live_verified_markup_adapters_and_global_share_style(self):
        # Container names/attributes observed on public publisher pages; text is synthetic.
        fixtures = {"meduza": '<div class="GeneralMaterial-module-article"><p>{}</p></div>',
                    "novayagazeta": '<article id="article"><div id="materialBlock_0" data-body="true"><p>{}</p></div></article>',
                    "currenttime": '<body class="use-sticky-share"><div class="body-container"><h1>Заголовок</h1><div class="wsw"><p>{}</p></div></div></body>',
                    "dw": '<article><div class="rich-text" data-tracking-name="rich-text"><p>{}</p></div></article>'}
        for key, template in fixtures.items():
            source = SOURCES[key]
            url = f"https://{source.host}/news/1"
            document = extract_article(template.format(BODY), url, source, FeedEntry(url, "Новость"))["document"]
            self.assertEqual(document["text"], BODY)

    def test_semantic_body_inside_recommendation_is_not_selected(self):
        source = SOURCES["rbc"]
        url = "https://www.rbc.ru/news/1"
        html = f'<div itemprop="articleBody">{BODY}</div><aside class="related-news"><div itemprop="articleBody">Все знают: неминуемая катастрофа.</div></aside>'
        self.assertEqual(extract_article(html, url, source, FeedEntry(url, "Новость"))["document"]["text"], BODY)

    def test_explicit_paywall_is_not_exported_as_a_complete_article(self):
        source = SOURCES["vedomosti"]
        url = "https://www.vedomosti.ru/news/1"
        data = {"@type": "NewsArticle", "url": url, "articleBody": BODY, "isAccessibleForFree": False}
        html = '<script type="application/ld+json">' + json.dumps(data) + '</script>'
        with self.assertRaisesRegex(ValueError, "платную"):
            extract_article(html, url, source, FeedEntry(url, "Новость"))
        for body in (BODY, None):
            data.pop("url", None)
            data["articleBody"] = body
            html = '<script type="application/ld+json">' + json.dumps(data) + f'</script><div itemprop="articleBody">{BODY}</div>'
            with self.assertRaisesRegex(ValueError, "платную"):
                extract_article(html, url, source, FeedEntry(url, "Новость"))


class TelegramTests(unittest.TestCase):
    def test_album_duplicate_nodes_are_removed_but_author_repetition_is_retained(self):
        source = SOURCES["aif_telegram"]
        caption = "Политики — свора. Политики — свора."
        html = telegram_post(1, caption, channel="aifonline").replace(
            '<a class="tgme_widget_message_link_preview">',
            '<div class="tgme_widget_message_text">' + caption + '</div><a class="tgme_widget_message_link_preview">')
        entry = parse_preview(html, source)[0]
        document = extract_post(html, entry.url, source, entry)["document"]
        self.assertEqual(document["text"], caption)
        self.assertEqual(len(analyze(document)["findings"]), 2)

    def test_all_three_requested_channels_are_distinct_and_usable(self):
        for source_id, channel, publisher in (("aif_telegram", "aifonline", "aif"),
                                               ("inosmi_telegram", "inosmichannel", "inosmi"),
                                               ("smotri_telegram", "smotri_media", "smotri")):
            with self.subTest(source=source_id):
                source = SOURCES[source_id]
                self.assertEqual((source.channel, source.publisher), (channel, publisher))
                entry = parse_preview(telegram_post(1, channel=channel), source)[0]
                self.assertEqual(entry.url, f"https://t.me/{channel}/1")
                self.assertEqual(extract_post(telegram_post(1, channel=channel), entry.url, source, entry)["document"]["text"], "Новость: открыта библиотека.")
        self.assertNotIn("smotri", PUBLISHERS)
        self.assertNotIn("smotri", SOURCES)

    def test_mediazona_channel_is_scoped_and_does_not_invent_a_website(self):
        source = SOURCES["mediazona_telegram"]
        self.assertEqual((source.channel, source.publisher, source.platform),
                         ("mediazzzona", "mediazona", "telegram"))
        markup = telegram_post(7, channel="mediazzzona")
        entry = parse_preview(markup, source)[0]
        self.assertEqual(entry.url, "https://t.me/mediazzzona/7")
        self.assertEqual(extract_post(markup, entry.url, source, entry)["document"]["text"],
                         "Новость: открыта библиотека.")
        with self.assertRaises(ValueError):
            normalize_url("https://t.me/mediazona/7", source)
        self.assertNotIn("mediazona", PUBLISHERS)

    source = SOURCES["rt_telegram"]

    def test_channel_scope_and_case_normalization(self):
        self.assertEqual(normalize_url("http://t.me/s/RT_RUSSIAN/42#top", self.source), "https://t.me/rt_russian/42")
        self.assertEqual(normalize_url("https://t.me/s/rt_russian?before=42", self.source), "https://t.me/s/rt_russian?before=42")
        self.assertEqual(normalize_url("https://t.me/rt_russian", self.source), "https://t.me/rt_russian")
        for path in ("/other_channel/42", "/rt_russian/0", "/rt_russian/42?embed=1", "/rt_russian/%34%32", "/rt_russian/../other_channel/42", "/s/rt_russian/42/extra", "/robots.txt", "/s/rt_russian?before=x", "/s/rt_russian?before=42&before=41"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                normalize_url("https://t.me" + path, self.source)
        with self.assertRaises(FetchError):
            PublisherRedirects(self.source).redirect_request(Request(self.source.feed_url), None, 302, "Found", {}, "https://t.me/other_channel/42")

    def test_preview_only_message_text_short_posts_captions_and_forward_context(self):
        html = ('<nav>Подписаться</nav>' + telegram_post(41) + telegram_post(42, "Срочно! Новый зал открыт.", forwarded="Forwarded from Редакция")
                + telegram_post(43, "", channel="rt_russian") + telegram_post(44, "Чужой текст", channel="other_channel"))
        entries = parse_preview(html, self.source)
        self.assertEqual([entry.url for entry in entries], ["https://t.me/rt_russian/42", "https://t.me/rt_russian/41"])
        extracted = extract_post(html, entries[0].url, self.source, entries[0])
        self.assertEqual(extracted["document"]["text"], "Forwarded from Редакция\nСрочно! Новый зал открыт.")
        self.assertEqual(extracted["document"]["title"], "")
        self.assertEqual(extracted["document"]["published_at"], "2026-10-11T09:00:00+00:00")
        self.assertEqual(extracted["extraction_method"], "telegram.public_message.forwarded")
        self.assertNotIn("катастрофа", extracted["document"]["text"])
        with self.assertRaises(ValueError):
            extract_post(html, "https://t.me/rt_russian/99", self.source, FeedEntry("https://t.me/rt_russian/99", ""))

    def test_inaccessible_or_media_only_preview_fails_explicitly(self):
        for html in ('<html>Sign in to Telegram</html>', telegram_post(41, ""), '<div data-post="rt_russian/41"><div class="tgme_widget_message_video">Видео</div></div>'):
            with self.assertRaises(ValueError):
                parse_preview(html, self.source)

    def test_html_blockquote_keeps_cited_statement_boundaries(self):
        from media_strazh.analysis import analyze
        html = telegram_post(41, 'В сообщении написано: <blockquote>Все знают о решении.</blockquote> Редакция проверяет информацию.')
        entry = parse_preview(html, self.source)[0]
        result = extract_post(html, entry.url, self.source, entry)
        self.assertIn("«Все знают о решении.»", result["document"]["text"])
        findings = analyze(result["document"])["findings"]
        self.assertTrue(findings)
        self.assertTrue(all(finding["status"] != "needs_review" for finding in findings))

    def test_robots_403_never_reads_full_telegram_posts_as_rss_discovery(self):
        client = SourceClient(self.source, minimum_delay=0)
        denied = HTTPError("https://t.me/robots.txt", 403, "Denied", {}, None)
        with patch.object(client, "_get", side_effect=denied) as fetch:
            with self.assertRaises(FetchError):
                client.get_feed()
        self.assertEqual(fetch.call_count, 1)

    def test_collector_reuses_preview_and_reextract_preserves_original_permalink(self):
        response = Response(self.source.feed_url, (telegram_post(41) + telegram_post(42)).encode(), "text/html", "utf-8")
        calls = []
        class Client:
            robots_error = None
            def get_feed(self): calls.append("preview"); return response
            def get(self, url): raise AssertionError("Visible posts should reuse the already fetched preview")
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "posts.sqlite3") as store:
            summary = collect_once(store, [self.source], limit=2, client_factory=lambda source: Client(), now=lambda: NOW)
            self.assertTrue(summary["success"])
            self.assertEqual(calls, ["preview"])
            self.assertEqual(store.status()["articles_collected"], 2)
            detail = store.article(store.articles()[0]["id"])
            self.assertIn(detail["document"]["url"], {"https://t.me/rt_russian/41", "https://t.me/rt_russian/42"})
            self.assertEqual(reextract_current(store)["processed"], 2)

    def test_unconfirmed_channel_is_visible_failure_while_other_source_completes(self):
        inactive = replace(SOURCES["tass_telegram"], channel="", feed_url="", configuration_error="Не подтверждён")
        response = Response(self.source.feed_url, telegram_post(41).encode(), "text/html", "utf-8")
        class Client:
            robots_error = None
            def get_feed(self): return response
            def get(self, url): return Response(url, b'<footer>No social address</footer>', "text/html")
        def factory(source):
            self.assertIn(source.id, {"tass", self.source.id})
            return Client()
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "posts.sqlite3") as store:
            summary = collect_once(store, [inactive, self.source], client_factory=factory, now=lambda: NOW)
            self.assertFalse(summary["success"])
            self.assertTrue(summary["sources"][self.source.id]["feed_ok"])
            self.assertIn("Telegram-канал", summary["sources"][inactive.id]["errors"][0]["error"])
            self.assertEqual(store.status()["articles_collected"], 1)

    def test_runtime_discovery_is_persisted_and_survives_reextract_and_restart(self):
        inactive = replace(SOURCES["tass_telegram"], channel="", feed_url="", configuration_error="Не подтверждён")
        home_calls = []
        class Client:
            robots_error = None
            def __init__(self, source): self.source = source
            def get(self, url):
                home_calls.append(url)
                return Response(url, b'<footer><a href="https://t.me/example_news">Telegram</a></footer>', "text/html")
            def get_feed(self):
                return Response(self.source.feed_url, telegram_post(41, channel="example_news").encode(), "text/html", "utf-8")
        with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "posts.sqlite3") as store, patch.dict(SOURCES, {inactive.id: inactive}):
            first = collect_once(store, [inactive], client_factory=Client, now=lambda: NOW)
            self.assertTrue(first["success"])
            self.assertEqual(store.status()["sources"][0]["feed_url"], "https://t.me/s/example_news")
            self.assertTrue(reextract_current(store)["success"])
            second = collect_once(store, [inactive], client_factory=Client, now=lambda: NOW)
            self.assertTrue(second["success"])
            self.assertEqual(home_calls, ["https://tass.ru/"])


class ExpandedNetworkTests(unittest.TestCase):
    def test_cycle_budget_records_remaining_sources_without_losing_completed_article(self):
        with patch("media_strazh.collector.time.monotonic", return_value=0) as clock:
            class Client:
                robots_error = None
                def __init__(self, source): self.source = source
                def get_feed(self):
                    url = f"https://{self.source.host}/news/1"
                    return Response(self.source.feed_url, f'<rss><channel><item><title>Новость</title><link>{url}</link></item></channel></rss>'.encode(), "application/rss+xml")
                def get(self, url):
                    clock.return_value = 20
                    return Response(url, f'<div itemprop="articleBody">{BODY}</div>'.encode(), "text/html")
            with tempfile.TemporaryDirectory() as directory, Store(Path(directory) / "articles.sqlite3") as store:
                summary = collect_once(store, [SOURCES[key] for key in ("rt", "tass", "ria")], client_factory=Client, now=lambda: NOW, time_budget_seconds=10)
                self.assertFalse(summary["success"])
                self.assertEqual(store.status()["articles_collected"], 1)
                self.assertEqual(len(store.status()["sources"]), 3)
                self.assertEqual(set(summary["sources"]), {"rt", "tass", "ria"})
                self.assertIn("бюджет", summary["sources"]["tass"]["errors"][0]["error"])

    def test_crawl_delay_longer_than_deadline_is_deferred_without_sleep(self):
        from urllib.robotparser import RobotFileParser
        robots = RobotFileParser()
        robots.parse(["User-agent: *", "Disallow:", "Crawl-delay: 1000"])
        state = {"robots": {"t.me": robots}, "robots_errors": {}, "last_requests": {"t.me": 0.0}}
        client = SourceClient(SOURCES["rt_telegram"], request_state=state, deadline=100, minimum_delay=2)
        with patch("media_strazh.network.time.monotonic", return_value=1), patch("media_strazh.network.time.sleep") as pause:
            with self.assertRaisesRegex(FetchError, "бюджет"):
                client._pace(client.source.feed_url)
        pause.assert_not_called()

    def test_stream_download_stops_when_deadline_expires_between_chunks(self):
        from email.message import Message
        client = SourceClient(SOURCES["ria"], minimum_delay=0, deadline=5)
        with patch("media_strazh.network.time.monotonic", return_value=0) as clock:
            class Stream:
                url = "https://ria.ru/news/1"
                headers = Message()
                headers["Content-Type"] = "text/html; charset=utf-8"
                reads = 0
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def read(self, size): raise AssertionError("Use bounded streaming read1 when available")
                def read1(self, size):
                    self.reads += 1
                    clock.return_value = 6
                    return b"first chunk"
            stream = Stream()
            with patch.object(client.opener, "open", return_value=stream) as opener:
                with self.assertRaisesRegex(FetchError, "бюджет"):
                    client._get(stream.url)
            self.assertEqual(stream.reads, 1)
            self.assertLessEqual(opener.call_args.kwargs["timeout"], 5)

    def test_html_challenge_does_not_count_as_valid_robots(self):
        client = SourceClient(SOURCES["meduza"], minimum_delay=0)
        response = Response("https://meduza.io/robots.txt", b"<html>Verify you are human</html>", "text/html")
        with patch.object(client, "_get", return_value=response) as fetch:
            with self.assertRaises(FetchError):
                client.get("https://meduza.io/news/1")
        self.assertEqual(fetch.call_count, 1)

    def test_redirect_target_requires_robots_and_channel_scope(self):
        client = SourceClient(SOURCES["rbc"], minimum_delay=0)
        denied = Response("https://www.rbc.ru/robots.txt", b"User-agent: *\nDisallow: /private/\n", "text/plain")
        with patch.object(client, "_get", return_value=denied):
            with self.assertRaises(FetchError):
                client._authorize_redirect("https://rbc.ru/article/1", "https://www.rbc.ru/private/1")
        with self.assertRaises(FetchError):
            client._authorize_redirect("https://rbc.ru/robots.txt", "https://www.rbc.ru/robots.txt")

    def test_robots_is_checked_for_feed_host_and_article_host_separately(self):
        client = SourceClient(SOURCES["rbc"], minimum_delay=0)
        allowed = b"User-agent: *\nDisallow:\n"
        responses = [Response("https://rssexport.rbc.ru/robots.txt", allowed, "text/plain"),
                     Response(SOURCES["rbc"].feed_url, b"<rss/>", "application/rss+xml"),
                     Response("https://www.rbc.ru/robots.txt", allowed, "text/plain"),
                     Response("https://www.rbc.ru/news/1", b"article", "text/html")]
        with patch.object(client, "_get", side_effect=responses) as fetch:
            client.get_feed(); client.get("https://www.rbc.ru/news/1")
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [response.url for response in responses])

    def test_public_telegram_clients_share_host_robots_and_pacing_state(self):
        state = {"robots": {}, "robots_errors": {}, "last_requests": {}}
        first = SourceClient(SOURCES["rt_telegram"], request_state=state, minimum_delay=0)
        second = SourceClient(SOURCES["ria_telegram"], request_state=state, minimum_delay=0)
        robots = Response("https://t.me/robots.txt", b"User-agent: *\nDisallow:\n", "text/plain")
        with patch.object(first, "_get", return_value=robots) as fetch1, patch.object(second, "_get") as fetch2:
            first.prepare(); second.prepare()
        self.assertEqual(fetch1.call_count, 1)
        self.assertEqual(fetch2.call_count, 0)
        self.assertIs(first.robots, second.robots)

    def test_host_pacing_applies_when_next_request_uses_another_channel(self):
        state = {"robots": {}, "robots_errors": {}, "last_requests": {"t.me": 10.0}}
        client = SourceClient(SOURCES["ria_telegram"], request_state=state, minimum_delay=2)
        with patch("media_strazh.network.time.monotonic", side_effect=[10.0, 12.0, 12.0]), patch("media_strazh.network.time.sleep") as pause:
            client._pace(client.source.feed_url)
        pause.assert_called_once_with(2.0)
        self.assertEqual(state["last_requests"]["t.me"], 12.0)

    def test_official_homepage_feed_discovery_rejects_external_rss(self):
        client = SourceClient(SOURCES["meduza"], minimum_delay=0)
        html = '<link rel="alternate" type="application/rss+xml" href="https://evil.example/rss"><link rel="alternate" type="application/rss+xml" href="/new-rss">'
        home = Response("https://meduza.io/", html.encode(), "text/html")
        rss = Response("https://meduza.io/new-rss", b"<rss/>", "application/rss+xml")
        with patch.object(client, "get", side_effect=[home, rss]) as fetch:
            self.assertEqual(client.discover_feed(), rss)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], ["https://meduza.io/", "https://meduza.io/new-rss"])


if __name__ == "__main__":
    unittest.main()

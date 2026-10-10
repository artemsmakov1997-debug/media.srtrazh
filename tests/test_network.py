import gzip
from unittest.mock import patch
import unittest
from urllib.error import HTTPError
from urllib.request import Request

from media_strazh.network import FetchError, MAX_DOWNLOAD, PublisherRedirects, Response, SourceClient
from media_strazh.sources import SOURCES


class NetworkTests(unittest.TestCase):
    def test_redirects_cannot_leave_publisher(self):
        handler = PublisherRedirects(SOURCES["ria"])
        request = Request("https://ria.ru/1")
        for target in ("https://127.0.0.1/", "https://tass.ru/1", "https://ria.ru.evil.example/1"):
            with self.assertRaises(FetchError):
                handler.redirect_request(request, None, 302, "Found", {}, target)

    def test_robots_denial_prevents_article_request(self):
        client = SourceClient(SOURCES["ria"], minimum_delay=0)
        robots = Response("https://ria.ru/robots.txt", b"User-agent: *\nDisallow: /private/\n", "text/plain")
        with patch.object(client, "_get", return_value=robots) as fetch:
            with self.assertRaises(FetchError):
                client.get("https://ria.ru/private/article")
        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(fetch.call_args.args[0], "https://ria.ru/robots.txt")

    def test_robots_403_blocks_collection_but_404_allows_it(self):
        client = SourceClient(SOURCES["rt"], minimum_delay=0)
        error = HTTPError("https://russian.rt.com/robots.txt", 403, "Denied", {}, None)
        with patch.object(client, "_get", side_effect=error):
            with self.assertRaises(FetchError):
                client.prepare()
        self.assertIsNone(client.robots)
        # A new collection cycle rechecks robots; one cycle caches the denial.
        client = SourceClient(SOURCES["rt"], minimum_delay=0)
        allowed = HTTPError("https://russian.rt.com/robots.txt", 404, "Missing", {}, None)
        page = Response("https://russian.rt.com/news/1", b"page", "text/html")
        with patch.object(client, "_get", side_effect=[allowed, page]):
            self.assertEqual(client.get(page.url), page)

    def test_http_retry_after_preserved(self):
        client = SourceClient(SOURCES["tass"], minimum_delay=0)
        robots = Response("https://tass.ru/robots.txt", b"User-agent: *\nDisallow:\n", "text/plain")
        error = HTTPError("https://tass.ru/news/1", 429, "Rate limit", {"Retry-After": "7200"}, None)
        with patch.object(client, "_get", side_effect=[robots, error]):
            with self.assertRaises(FetchError) as caught:
                client.get("https://tass.ru/news/1")
        self.assertEqual(caught.exception.retry_after, 7200)

    def test_decoding_declared_charset_and_failure(self):
        response = Response("https://ria.ru/1", '<meta charset="windows-1251">Привет'.encode("cp1251"), "text/html")
        self.assertIn("Привет", response.text())
        with self.assertRaises(FetchError):
            Response("https://ria.ru/1", b"\xff", "text/html", "utf-8").text()

    def test_public_rss_can_be_discovered_when_robots_is_403_but_articles_stay_blocked(self):
        client = SourceClient(SOURCES["tass"], minimum_delay=0)
        denied = HTTPError("https://tass.ru/robots.txt", 403, "Denied", {}, None)
        feed = Response(SOURCES["tass"].feed_url, b"<rss/>", "application/rss+xml")
        with patch.object(client, "_get", side_effect=[denied, feed]) as fetch:
            self.assertEqual(client.get_feed(), feed)
            with self.assertRaises(FetchError):
                client.get("https://tass.ru/news/1")
        self.assertEqual(fetch.call_count, 2)

    def test_known_robots_disallow_still_applies_to_rss(self):
        client = SourceClient(SOURCES["rt"], minimum_delay=0)
        robots = Response("https://russian.rt.com/robots.txt", b"User-agent: *\nDisallow: /rss\n", "text/plain")
        with patch.object(client, "_get", return_value=robots) as fetch:
            with self.assertRaises(FetchError):
                client.get_feed()
        self.assertEqual(fetch.call_count, 1)

    def test_response_size_and_gzip_expansion_are_bounded(self):
        from email.message import Message
        import io
        class FakeResponse:
            def __init__(self, data, encoding):
                self.body = io.BytesIO(data)
                self.url = "https://ria.ru/1"
                self.headers = Message()
                self.headers["Content-Type"] = "text/html; charset=utf-8"
                self.headers["Content-Encoding"] = encoding
            def __enter__(self): return self
            def __exit__(self, *args): self.body.close()
            def read(self, size): return self.body.read(size)
        for data, encoding in [(b"x" * (MAX_DOWNLOAD + 1), "identity"),
                               (gzip.compress(b"x" * (MAX_DOWNLOAD + 1)), "gzip")]:
            client = SourceClient(SOURCES["ria"], minimum_delay=0)
            with patch.object(client.opener, "open", return_value=FakeResponse(data, encoding)):
                with self.assertRaises(FetchError):
                    client._get("https://ria.ru/1")


if __name__ == "__main__":
    unittest.main()

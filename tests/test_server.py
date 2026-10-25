import json
from dataclasses import replace
from pathlib import Path
import tempfile
from http.server import ThreadingHTTPServer
from threading import Thread
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from media_strazh.server import Handler
from media_strazh.analysis import VERSION
from media_strazh.sources import SOURCES, resolve_source
from media_strazh.storage import Store, utcnow


class QuietHandler(Handler):
    def log_message(self, *args):
        pass


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, document, content_type="application/json"):
        return urlopen(Request(self.base + "/api/v1/analyze", data=json.dumps(document, ensure_ascii=False).encode(), headers={"Content-Type": content_type}), timeout=5)

    def test_health_and_form(self):
        with urlopen(self.base + "/health") as response:
            self.assertEqual(json.load(response)["status"], "ok")
        with urlopen(self.base + "/") as response:
            self.assertIn("Разбор публикации", response.read().decode())

    def test_api_returns_analysis_of_submitted_text(self):
        with self.post({"title": "Решение", "text": "Все знают о решении."}) as response:
            result = json.load(response)
        self.assertEqual(result["summary"]["review_candidates"], 1)
        self.assertEqual(result["findings"][0]["evidence"][0]["quote"], "Все знают")

    def test_bad_document(self):
        with self.assertRaises(HTTPError) as error:
            self.post({"text": ""})
        self.assertEqual(error.exception.code, 400)

    def test_expanded_rules_available_through_api(self):
        with self.post({"text": "Политики опасны без смирительной рубашки. Война как единственный выход."}) as response:
            result = json.load(response)
        self.assertEqual(result["algorithm_version"], VERSION)
        self.assertEqual(set(result["summary"]["by_category"]), {"enemy_image", "euphemism_dysphemism", "oversimplification"})
        self.assertEqual(result["summary"]["review_fragments"], 2)

    def test_bad_json(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(Request(self.base + "/api/v1/analyze", data=b'{bad', headers={"Content-Type": "application/json"}))
        self.assertEqual(error.exception.code, 400)

    def test_content_type(self):
        with self.assertRaises(HTTPError) as error:
            self.post({"text": "Текст статьи."}, "text/plain")
        self.assertEqual(error.exception.code, 415)

    def test_unknown_route_and_taxonomy(self):
        with self.assertRaises(HTTPError) as error:
            urlopen(self.base + "/secret-file")
        self.assertEqual(error.exception.code, 404)
        with urlopen(self.base + "/api/v1/taxonomy") as response:
            categories = json.load(response)["categories"]
            self.assertEqual(len(categories), 16)
            self.assertEqual(next(c for c in categories if c["id"] == "event_terminology")["coverage"],
                             "context_notices")

    def test_source_registry_available_without_collection_database(self):
        with urlopen(self.base + "/api/v1/sources") as response:
            entries = json.load(response)["sources"]
        self.assertEqual({entry["id"] for entry in entries}, set(SOURCES))
        self.assertEqual({entry["publisher_id"] for entry in entries},
                         {source.publisher for source in SOURCES.values()})
        telegram = [entry for entry in entries if entry["platform"] == "telegram"]
        self.assertTrue(telegram)
        self.assertTrue(all(entry["id"].endswith("_telegram") for entry in telegram))

    def test_source_registry_reflects_persisted_channel_discovery(self):
        pending = replace(SOURCES["interfax_telegram"], channel="", feed_url="",
                          configuration_error="Канал требует подтверждения")
        with tempfile.TemporaryDirectory() as directory, patch.dict(SOURCES, {pending.id: pending}):
            path = Path(directory) / "sources.sqlite3"
            source = resolve_source(SOURCES["interfax_telegram"], "https://t.me/s/fixture_channel")
            with Store(path) as store:
                store.source_result(source, utcnow(), True)
            self.server.db_path = path
            try:
                with urlopen(self.base + "/api/v1/sources") as response:
                    entries = json.load(response)["sources"]
                entry = next(entry for entry in entries if entry["id"] == source.id)
                self.assertEqual(entry["channel"], "fixture_channel")
                self.assertEqual(entry["configuration_error"], "")
                self.assertEqual(entry["publisher_id"], "interfax")
            finally:
                del self.server.db_path


if __name__ == "__main__":
    unittest.main()

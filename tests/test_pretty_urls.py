"""Contract tests for GitHub Pages clean URL aliases."""
import tempfile
import unittest
from pathlib import Path

from media_strazh.pretty_urls import CLEAN_ROUTES, publish_clean_routes
from media_strazh.publishing import ROOT


class CleanRoutesTest(unittest.TestCase):
    def test_clean_pages_work_without_renaming_original_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            for slug in ("index", *CLEAN_ROUTES):
                (site / f"{slug}.html").write_bytes((ROOT / f"{slug}.html").read_bytes())
            (site / "pro-gateway.js").write_bytes((ROOT / "pro-gateway.js").read_bytes())
            (site / "sitemap.xml").write_bytes((ROOT / "sitemap.xml").read_bytes())

            publish_clean_routes(site)
            for slug in CLEAN_ROUTES:
                url = f"/{slug}/"
                copy = (site / slug / "index.html").read_text(encoding="utf-8")
                legacy = (site / f"{slug}.html").read_text(encoding="utf-8")
                self.assertIn('<base href="/">', copy)
                self.assertIn(f'<link rel="canonical" href="https://media-strazh.ru{url}">', copy)
                self.assertIn(f"location.replace('{url}'", legacy)
                self.assertIn(f"location.pathname==='/{slug}.html'", legacy)
                self.assertNotIn('<base href="/">', legacy)
                self.assertNotIn(f'href="{slug}.html"', copy)

            self.assertIn('href="/#appeal"', (site / "index.html").read_text(encoding="utf-8"))
            help_alias = (site / "help" / "index.html").read_text(encoding="utf-8")
            self.assertIn('href="/help/#supportFormats"', help_alias)
            self.assertIn('href="/analysis/"', (site / "pro-gateway.js").read_text(encoding="utf-8"))
            self.assertIn('href="/business/"', (site / "pro-gateway.js").read_text(encoding="utf-8"))
            self.assertIn('location.pathname===\'/index.html\'', (site / "index.html").read_text())
            sitemap = (site / "sitemap.xml").read_text()
            self.assertIn('https://media-strazh.ru/method/', sitemap)
            self.assertNotIn('method.html', sitemap)

    def test_legacy_urls_keep_query_and_fragment(self):
        with tempfile.TemporaryDirectory() as temp:
            site = Path(temp)
            for slug in ("index", *CLEAN_ROUTES):
                (site / f"{slug}.html").write_text(
                    '<html><head></head><body><a href="index.html">Home</a></body></html>',
                    encoding="utf-8")
            publish_clean_routes(site)
            redirect = (site / "analysis.html").read_text()
            self.assertIn("location.search+location.hash", redirect)
            clean = (site / "analysis" / "index.html").read_text()
            self.assertIn('href="/"', clean)
            self.assertNotIn('location.replace(', clean)


if __name__ == "__main__":
    unittest.main()

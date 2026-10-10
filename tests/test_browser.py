from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from media_strazh.browser import prepare_runtime, runtime_assets
from browser_fixtures import runtime_fixture


class BrowserRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.runtime = runtime_fixture(self.path / "runtime")

    def tearDown(self):
        self.directory.cleanup()

    def test_modified_runtime_file_is_rejected(self):
        (self.runtime / "pyodide.js").write_text("changed")
        with self.assertRaisesRegex(ValueError, "повреждён"):
            runtime_assets(self.runtime)

    def test_missing_runtime_cannot_be_published(self):
        (self.runtime / "python_stdlib.zip").unlink()
        with self.assertRaisesRegex(ValueError, "повреждён"):
            runtime_assets(self.runtime)

    def test_symlink_runtime_file_is_rejected(self):
        path = self.runtime / "pyodide.js"
        target = self.path / "external.js"
        target.write_bytes(path.read_bytes())
        path.unlink()
        path.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "повреждён"):
            runtime_assets(self.runtime)

    def test_wrong_archive_checksum_does_not_modify_existing_runtime(self):
        before = (self.runtime / "pyodide.js").read_bytes()
        archive = self.path / "bad.tgz"
        archive.write_bytes(b"not the official archive")
        with self.assertRaisesRegex(ValueError, "SHA-512"):
            prepare_runtime(self.runtime, archive)
        self.assertEqual((self.runtime / "pyodide.js").read_bytes(), before)

    def test_verified_local_runtime_is_reused_without_network(self):
        with patch("media_strazh.browser.urlopen") as network:
            result = prepare_runtime(self.runtime)
        self.assertTrue(result["cached"])
        network.assert_not_called()

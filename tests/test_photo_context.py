"""Pure browser-algorithm fixtures, without third-party JS packages."""
from pathlib import Path
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which('node'), 'Node is optional locally; photo browser checks run in Actions')
class PhotoContextCoreTests(unittest.TestCase):
    def test_photo_evidence_algorithms(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(root / 'tests/photo_context_core_check.cjs')],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

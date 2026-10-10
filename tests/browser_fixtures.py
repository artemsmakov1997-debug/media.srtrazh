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

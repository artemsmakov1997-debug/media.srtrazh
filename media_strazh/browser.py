"""Verified, self-hosted Python runtime and the existing analysis code for browsers."""

import base64
import hashlib
import io
import json
from pathlib import Path
import tarfile
from urllib.request import urlopen

from .analysis import MAX_CHARS, VERSION

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNTIME = ROOT / "_runtime" / "pyodide"
RUNTIME_VERSION = "0.29.3"
RUNTIME_URL = f"https://registry.npmjs.org/pyodide/-/pyodide-{RUNTIME_VERSION}.tgz"
RUNTIME_INTEGRITY = "22UBuhOJawj7vKUnS7/F3xK+515LJdjiMAHoCfuS6/PbHiOrSQVnYwDe+2sbVwiOZ3sMMexdXICew6NqOMQGgA=="
RUNTIME_FILES = ("pyodide.js", "pyodide.asm.js", "pyodide.asm.wasm",
                 "python_stdlib.zip", "pyodide-lock.json")
ENGINE_FILES = ("__init__.py", "analysis.py", "rules.py")
MANIFEST = "runtime-manifest.json"


def runtime_assets(directory):
    """Reject missing or altered runtime files before publishing the site."""
    directory = Path(directory)
    manifest_path = directory / MANIFEST
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise ValueError("Сначала выполните python3 -m media_strazh prepare-browser.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (manifest.get("version") != RUNTIME_VERSION or
            manifest.get("archive_sha512") != RUNTIME_INTEGRITY or
            set(manifest.get("files", {})) != set(RUNTIME_FILES)):
        raise ValueError("Версия браузерного движка не совпадает; повторите prepare-browser.")
    assets = {MANIFEST: manifest_path}
    for name in RUNTIME_FILES:
        path = directory / name
        if (not path.is_file() or path.is_symlink() or
                hashlib.sha256(path.read_bytes()).hexdigest() != manifest["files"][name]):
            raise ValueError(f"Браузерный движок повреждён: {name}; повторите prepare-browser.")
        assets[name] = path
    assets["LICENSE.txt"] = ROOT / "third_party" / "PYODIDE-LICENSE.txt"
    assets["NOTICE.txt"] = ROOT / "third_party" / "PYODIDE-NOTICE.txt"
    return assets


def prepare_runtime(directory=DEFAULT_RUNTIME, archive_path=None):
    directory = Path(directory).resolve()
    if directory == ROOT or ROOT.is_relative_to(directory):
        raise ValueError("Используйте отдельный каталог браузерного движка.")
    if directory.is_relative_to(ROOT) and directory.relative_to(ROOT).parts[0] != "_runtime":
        raise ValueError("Внутри репозитория используйте каталог _runtime.")
    if archive_path is None:
        try:
            assets = runtime_assets(directory)
            return {"version": RUNTIME_VERSION, "directory": str(directory), "cached": True,
                    "bytes": sum(path.stat().st_size for path in assets.values())}
        except (OSError, ValueError):
            pass
        with urlopen(RUNTIME_URL, timeout=60) as response:
            archive = response.read(20_000_001)
    else:
        archive = Path(archive_path).read_bytes()
    if len(archive) > 20_000_000:
        raise ValueError("Архив браузерного движка превышает ограничение размера.")
    if base64.b64encode(hashlib.sha512(archive).digest()).decode() != RUNTIME_INTEGRITY:
        raise ValueError("Контрольная сумма SHA-512 браузерного движка не совпадает.")
    contents = {}
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as package:
        for name in RUNTIME_FILES:
            member = package.getmember("package/" + name)
            if not member.isfile():
                raise ValueError("Недопустимый файл браузерного движка.")
            contents[name] = package.extractfile(member).read()
    directory.mkdir(parents=True, exist_ok=True)
    for name, data in contents.items():
        target = directory / name
        if target.is_symlink():
            raise ValueError("Каталог браузерного движка содержит символическую ссылку.")
        target.write_bytes(data)
    manifest_path = directory / MANIFEST
    if manifest_path.is_symlink():
        raise ValueError("Каталог браузерного движка содержит символическую ссылку.")
    manifest = {"version": RUNTIME_VERSION, "archive_sha512": RUNTIME_INTEGRITY,
                "files": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()}}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    assets = runtime_assets(directory)
    return {"version": RUNTIME_VERSION, "directory": str(directory), "cached": False,
            "bytes": sum(path.stat().st_size for path in assets.values())}


def engine_bundle():
    """The same Python source as the CLI/API; no second catalogue or JS rule engine."""
    return {"schema_version": "browser-engine-1.0", "algorithm_version": VERSION,
            "max_chars": MAX_CHARS, "runtime_version": RUNTIME_VERSION,
            "files": {name: (ROOT / "media_strazh" / name).read_text(encoding="utf-8")
                      for name in ENGINE_FILES}}

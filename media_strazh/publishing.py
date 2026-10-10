"""Static, bounded reports for a GitHub Pages pilot; no article bodies or database."""

import json
from pathlib import Path
import shutil
import tempfile

from .analysis import VERSION, taxonomy
from .sources import SOURCES, normalize_url
from .storage import utcnow

SCHEMA = "public-snapshot-1.0"
ROOT = Path(__file__).resolve().parents[1]
STATIC_SUFFIXES = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".gif",
                   ".webp", ".svg", ".ico", ".webmanifest", ".xml"}


def snapshot(store, limit=30):
    if not 1 <= limit <= 100:
        raise ValueError("Размер подборки должен быть от 1 до 100 публикаций.")
    store.db.execute("SAVEPOINT public_snapshot")
    try:
        status = store.status()
        articles = []
        for row in store.articles(limit=limit):
            item = store.article(row["id"])
            document, analysis = item["document"], item["analysis"]
            source = SOURCES[item["source_id"]]
            findings = []
            if analysis:
                for finding in analysis["findings"][:40]:
                    findings.append({
                        key: finding[key] for key in
                        ("category", "label", "rule_id", "status", "explanation", "review_question", "evidence")
                    })
            articles.append({
                "id": item["id"], "source_id": source.id, "source": source.name,
                "title": document["title"], "url": normalize_url(document["url"], source),
                "published_at": document["published_at"], "retrieved_at": item["retrieved_at"],
                "algorithm_version": analysis["algorithm_version"] if analysis else None,
                "sha256": analysis["document"]["sha256"] if analysis else None,
                "summary": analysis["summary"] if analysis else None,
                "findings": findings,
                "findings_omitted": max(0, len(analysis["findings"]) - len(findings)) if analysis else 0,
            })
        analyzed = [item for item in articles if item["summary"] is not None]
        if not analyzed:
            raise ValueError("Нет публикаций с анализом текущей версии; предыдущий сайт не заменён.")
        return {
            "schema_version": SCHEMA, "generated_at": utcnow(), "algorithm_version": VERSION,
            "coverage": taxonomy(), "articles": articles,
            "totals": {"displayed": len(articles), "analyzed": len(analyzed),
                       "with_review_candidates": sum(item["summary"]["review_fragments"] > 0
                                                     for item in analyzed),
                       "review_fragments": sum(item["summary"]["review_fragments"] for item in analyzed)},
            "sources": [
                {"id": source.id, "name": source.name,
                 "displayed": sum(item["source_id"] == source.id for item in articles),
                 "status": next(({
                     key: saved[key] for key in
                     ("last_attempt_at", "last_success_at", "last_error", "next_attempt_at")
                 } for saved in status["sources"] if saved["source_id"] == source.id), None)}
                for source in SOURCES.values()
            ],
        }
    finally:
        store.db.execute("RELEASE public_snapshot")


def build_site(store, output, limit=30):
    """Build only public root assets and selected report fields in a generated directory."""
    destination = Path(output).resolve()
    if destination == ROOT or ROOT.is_relative_to(destination):
        raise ValueError("Используйте отдельный каталог сборки, например _site.")
    if destination.is_relative_to(ROOT):
        relative = destination.relative_to(ROOT)
        if relative.parts[0] != "_site":
            raise ValueError("Внутри репозитория используйте каталог _site.")
    assets = [path for path in ROOT.iterdir() if path.is_file() and not path.is_symlink()
              and (path.suffix.lower() in STATIC_SUFFIXES or path.name in {"CNAME", "robots.txt"})]
    allowed = {Path(path.name) for path in assets} | {Path("data/analysis.json")}
    if destination.exists():
        for path in destination.rglob("*"):
            if path.is_symlink() or (not path.is_dir() and path.relative_to(destination) not in allowed):
                raise ValueError("В каталоге сборки есть посторонние файлы; используйте пустой каталог.")
    report = snapshot(store, limit)  # Validate before modifying any earlier output.
    destination.mkdir(parents=True, exist_ok=True)
    for path in assets:
        shutil.copy2(path, destination / path.name)
    report_path = destination / "data" / "analysis.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=report_path.parent,
                                         suffix=".tmp", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(report, handle, ensure_ascii=False)
            handle.write("\n")
        temporary.replace(report_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"output": str(destination), "totals": report["totals"],
            "algorithm_version": report["algorithm_version"]}

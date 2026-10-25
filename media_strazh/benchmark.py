"""Reproducible, unlabelled corpus preparation and human-confirmed span evaluation."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re
import shutil
import unicodedata

from .analysis import SUPPORTED, VERSION, analyze, taxonomy
from .sources import SOURCES

SCHEMA = "review-corpus-1.0"
KNOWN_DEVELOPMENT_URLS = {
    "https://t.me/izvestia/253503", "https://t.me/radiosvoboda/105417",
    "https://t.me/inosmichannel/32847", "https://t.me/medvedev_telegram/666",
    "https://russian.rt.com/opinion/1692015-rudalev-voina-krizis-evropa",
    "https://russiatoday.ru/opinion/1692015-rudalev-voina-krizis-evropa",
    "https://russiatoday.ru/world/article/1693370-ssha-ukraina-npz-rossiya",
    "https://t.me/inosmichannel/32784", "https://t.me/inosmichannel/32786",
    "https://t.me/inosmichannel/32771", "https://t.me/inosmichannel/32777",
    "https://t.me/aifonline/200975",
    "https://t.me/vatnoeboloto/4366", "https://t.me/vatnoeboloto/15114",
}


def _hash(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def prepare_benchmark(store, output, size=240, seed="pilot-2026-1"):
    if not 3 <= size <= 1000:
        raise ValueError("Размер корпуса должен быть от 3 до 1000.")
    output = Path(output)
    if output.exists():
        raise ValueError("Для корпуса нужен новый каталог; существующая разметка не заменяется.")
    groups, seen_urls, seen_text, anchors = defaultdict(list), set(), set(), defaultdict(list)
    fingerprints, excluded, duplicates = [], 0, 0
    for row in store.export_corpus():
        document = row["document"]
        url = document["url"].rstrip("/")
        if url in KNOWN_DEVELOPMENT_URLS:
            excluded += 1
            continue
        words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", document["text"]).casefold())
        text_hash = _hash(" ".join(words))
        shingles = {_hash(" ".join(words[i:i + 5]))[:16] for i in range(max(0, len(words) - 4))}
        keys = sorted(shingles)[:16]
        candidates = {index for key in keys for index in anchors[key]}
        near = any(len(shingles & fingerprints[index]) / max(1, len(shingles | fingerprints[index])) >= .85
                   for index in candidates)
        if url in seen_urls or text_hash in seen_text or near:
            duplicates += 1
            continue
        seen_urls.add(url)
        seen_text.add(text_hash)
        for key in keys:
            anchors[key].append(len(fingerprints))
        fingerprints.append(shingles)
        source_id = row["id"].split(":", 1)[0]
        source = SOURCES.get(source_id)
        if source is None:
            continue
        row.update(schema_version=SCHEMA, split=None, reviewer="", reviewed_at=None, spans=[])
        row["provenance"].update(source_id=source_id, publisher_id=source.publisher, platform=source.platform)
        content = {"title": document.get("title", ""), "text": document["text"],
                   **({"media": document["media"]} if "media" in document else {})}
        row["provenance"]["sha256"] = _hash(json.dumps(content,
                                                      ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        # No detector labels or scores participate in selection or reviewer input.
        length = "short" if len(words) < 100 else "medium" if len(words) < 500 else "long"
        groups[(source_id, length)].append(row)
    for group in groups.values():
        group.sort(key=lambda row: _hash(seed + row["provenance"]["sha256"]))
    selected = []
    ordered = sorted(groups, key=lambda key: _hash(seed + repr(key)))
    while len(selected) < size and any(groups.values()):
        for key in ordered:
            if groups[key] and len(selected) < size:
                selected.append(groups[key].pop())
    if len(selected) != size:
        raise ValueError(f"После исключений и удаления дублей доступно {len(selected)} публикаций; требуется {size}.")
    selected.sort(key=lambda row: _hash("split:" + seed + row["provenance"]["sha256"]))
    holdout = max(1, size // 3)
    for index, row in enumerate(selected):
        row["split"] = "holdout" if index < holdout else "development"
    manifest = {
        "schema_version": SCHEMA, "seed": seed, "size": size,
        "sampling": "source_length_stratified_hash_without_detector_labels",
        "deduplication": "URL, normalized text; shared-minimum-shingle Jaccard >= 0.85 (heuristic)",
        "excluded_known_development": excluded, "duplicates_excluded": duplicates,
        "splits": dict(Counter(row["split"] for row in selected)),
        "sources": dict(Counter(row["provenance"]["source_id"] for row in selected)),
        "platforms": dict(Counter(row["provenance"]["platform"] for row in selected)),
        "categories": [item for item in taxonomy() if item["id"] in SUPPORTED],
        "documents": [{"id": row["id"], "sha256": row["provenance"]["sha256"], "split": row["split"]} for row in selected],
        "annotation_status": "awaiting_human_review", "algorithm_version_at_preparation": VERSION,
        "note": "Это диагностическая выборка, а не репрезентативная статистика СМИ. Отложенную часть не использовать для настройки правил.",
    }
    output.mkdir(parents=True)
    for split in ("development", "holdout"):
        with (output / (split + ".jsonl")).open("x", encoding="utf-8") as target:
            for row in selected:
                if row["split"] == split:
                    target.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copyfile(Path(__file__).with_name("annotation.html"), output / "annotation.html")
    (output / "README.txt").write_text(
        "Откройте annotation.html и выберите development.jsonl. Введите имя проверяющего. "
        "Выделите фрагмент в заголовке или тексте, укажите приём и чей это голос. "
        "После проверки всего документа нажмите «Документ проверен». "
        "Для текста без признаков оставьте список пустым и подтвердите проверку. "
        "Регулярно скачивайте JSONL: это основной переносимый файл разметки. "
        "Отложенные holdout.jsonl размечайте после фиксации версии алгоритма; не используйте для настройки. "
        "Оценка: python3 -m media_strazh evaluate-benchmark --file reviewed.jsonl --split development\n",
        encoding="utf-8")
    return {"output": str(output), "size": size, "splits": manifest["splits"], "sources": len(manifest["sources"]),
            "annotation_status": manifest["annotation_status"]}


def _score(tp, fp, fn):
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}


def evaluate_benchmark(records, split="development", manifest=None):
    if split not in {"development", "holdout"}:
        raise ValueError("Неизвестная часть корпуса.")
    seen, hashes, completed, pending, uncertain = set(), set(), 0, 0, 0
    by_category = {key: [0, 0, 0] for key in sorted(SUPPORTED)}
    statuses = {key: [0, 0, 0] for key in ("needs_review", "quoted_candidate", "context_only")}
    span_categories = {key: [0, 0, 0] for key in sorted(SUPPORTED)}
    expected_documents = {row["id"]: row for row in (manifest or {}).get("documents", [])}
    exact, overlap, voice_correct, voice_total, errors = [0, 0, 0], [0, 0, 0], 0, 0, []
    for row in records:
        if not isinstance(row, dict) or row.get("schema_version") != SCHEMA or row.get("split") not in {"development", "holdout"} or not isinstance(row.get("id"), str):
            raise ValueError("Ожидается документ подготовленного проверочного корпуса.")
        if row["id"] in seen:
            raise ValueError("Повторяющийся id корпуса.")
        seen.add(row["id"])
        original = expected_documents.get(row["id"])
        if manifest is not None and (not original or original["split"] != row["split"]):
            raise ValueError("Документ или часть корпуса не соответствует исходному манифесту.")
        if row["split"] != split:
            continue
        result = analyze(row["document"])
        digest = result["document"]["sha256"]
        if digest != row.get("provenance", {}).get("sha256") or digest in hashes or (original and digest != original["sha256"]):
            raise ValueError("Изменён оригинал или повторяется документ; разметку нужно проверить заново.")
        hashes.add(digest)
        if row.get("fully_annotated") is not True:
            pending += 1
            continue
        if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
            raise ValueError("У проверенного документа должен быть указан проверяющий.")
        categories = row.get("annotation_categories")
        if not isinstance(categories, list) or any(not isinstance(c, str) for c in categories) or len(categories) != len(SUPPORTED) or set(categories) != SUPPORTED:
            raise ValueError("Проверены не все поддерживаемые категории.")
        labels = row.get("labels")
        if not isinstance(labels, list) or any(not isinstance(c, str) for c in labels) or len(set(labels)) != len(labels):
            raise ValueError("Нужны явные метки документа; для проверенного отрицательного примера labels=[].")
        gold = row.get("spans")
        if not isinstance(gold, list):
            raise ValueError("Нужен список размеченных фрагментов.")
        for span in gold:
            if not isinstance(span, dict):
                raise ValueError("Некорректный фрагмент разметки.")
            field, start, end = span.get("field"), span.get("start"), span.get("end")
            value = row["document"].get(field, "") if isinstance(field, str) else ""
            if (not isinstance(field, str) or field not in {"title", "text"} or type(start) is not int or type(end) is not int
                    or not 0 <= start < end <= len(value) or span.get("quote") != value[start:end]
                    or not isinstance(span.get("category"), str) or span["category"] not in SUPPORTED
                    or not isinstance(span.get("status"), str) or span["status"] not in {*statuses, "uncertain"}):
                raise ValueError("Некорректные координаты, цитата, категория или голос разметки.")
        if any(span["status"] == "uncertain" for span in gold):
            uncertain += 1
            continue
        if result["summary"]["findings_truncated"]:
            raise ValueError("Усечённый анализ нельзя включать в оценку.")
        completed += 1
        if len({(s["field"], s["start"], s["end"], s["category"], s["status"]) for s in gold}) != len(gold):
            raise ValueError("Повторяющиеся фрагменты разметки.")
        predicted = [dict(e, category=f["category"], status=f["status"], rule_id=f["rule_id"]) for f in result["findings"]
                     if f["category"] in SUPPORTED for e in f["evidence"]]
        predicted = list({(p["field"], p["start"], p["end"], p["category"], p["status"]): p for p in predicted}.values())
        labels = {p["category"] for p in predicted if p["status"] == "needs_review"}
        expected = {p["category"] for p in gold if p["status"] == "needs_review"}
        if set(row.get("labels") or []) != expected:
            raise ValueError("Категории документа не соответствуют его размеченным фрагментам.")
        for category, counts in by_category.items():
            counts[0] += int(category in labels and category in expected)
            counts[1] += int(category in labels and category not in expected)
            counts[2] += int(category not in labels and category in expected)
        matches = []
        for pi, pred in enumerate(predicted):
            for gi, target in enumerate(gold):
                if pred["field"] != target["field"] or pred["category"] != target["category"]:
                    continue
                intersection = max(0, min(pred["end"], target["end"]) - max(pred["start"], target["start"]))
                union = max(pred["end"], target["end"]) - min(pred["start"], target["start"])
                if intersection / union >= .5:
                    matches.append((intersection / union, pi, gi))
        used_p, used_g, hit, strict = set(), set(), 0, 0
        for iou, pi, gi in sorted(matches, reverse=True):
            if pi in used_p or gi in used_g:
                continue
            used_p.add(pi); used_g.add(gi)
            pred, target = predicted[pi], gold[gi]
            voice_total += 1
            same_voice = pred["status"] == target["status"]
            voice_correct += int(same_voice)
            hit += int(same_voice)
            strict += int(same_voice and iou == 1)
            if same_voice:
                statuses[target["status"]][0] += 1
                span_categories[target["category"]][0] += 1
            else:
                statuses[pred["status"]][1] += 1
                statuses[target["status"]][2] += 1
                span_categories[pred["category"]][1] += 1
                span_categories[target["category"]][2] += 1
        for pi, pred in enumerate(predicted):
            if pi not in used_p:
                statuses[pred["status"]][1] += 1
                span_categories[pred["category"]][1] += 1
        for gi, target in enumerate(gold):
            if gi not in used_g:
                statuses[target["status"]][2] += 1
                span_categories[target["category"]][2] += 1
        for count, correct in ((exact, strict), (overlap, hit)):
            count[0] += correct; count[1] += len(predicted) - correct; count[2] += len(gold) - correct
        if len(errors) < 200 and (hit != len(gold) or hit != len(predicted)):
            errors.append({"id": row["id"], "url": row["document"].get("url"), "expected": gold, "predicted": predicted})
    if not hashes:
        raise ValueError("В файле нет документов выбранной части корпуса.")
    pending += sum(row["split"] == split and row["id"] not in seen for row in expected_documents.values())
    return {"algorithm_version": VERSION, "split": split, "reviewed": completed, "pending": pending,
            "unresolved": uncertain, "status": "awaiting_human_review" if not completed else "partial" if pending or uncertain else "reviewed",
            "metrics": {"document_category_author": {key: _score(*value) for key, value in by_category.items()},
                        "exact_spans_with_status": _score(*exact), "overlap_iou_0.5_with_status": _score(*overlap),
                        "by_status": {key: _score(*value) for key, value in statuses.items()},
                        "spans_by_category": {key: _score(*value) for key, value in span_categories.items()},
                        "voice_accuracy_on_matched_spans": voice_correct / voice_total if voice_total else None} if completed else None,
            "errors": errors, "note": "Метки подтверждены указанным проверяющим; один человек и диагностическая выборка не устанавливают объективную истину или общую точность для всех СМИ."}

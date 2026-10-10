"""Document/category evaluation against complete human annotation."""

from .analysis import SUPPORTED, analyze


def evaluate(records):
    counts = {key: {"tp": 0, "fp": 0, "fn": 0, "support": 0} for key in sorted(SUPPORTED)}
    seen = set()
    for row in records:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"].strip():
            raise ValueError("Каждой статье нужен непустой строковый id.")
        if row["id"] in seen:
            raise ValueError("Повторяющийся id статьи в корпусе.")
        seen.add(row["id"])
        if row.get("fully_annotated") is not True:
            raise ValueError("Для оценки нужна полная разметка: fully_annotated=true.")
        annotation_categories = row.get("annotation_categories")
        if (not isinstance(annotation_categories, list)
                or any(not isinstance(key, str) for key in annotation_categories)
                or len(set(annotation_categories)) != len(annotation_categories)
                or set(annotation_categories) != SUPPORTED):
            raise ValueError("annotation_categories должен перечислять все текущие поддерживаемые категории. "
                             "Разметку старых версий нужно дополнить перед оценкой.")
        labels = row.get("labels")
        if not isinstance(labels, list) or any(not isinstance(label, str) for label in labels):
            raise ValueError("labels должен быть списком идентификаторов категорий.")
        if set(labels) - SUPPORTED:
            raise ValueError("В этой оценке допустимы только поддерживаемые категории: " + ", ".join(sorted(SUPPORTED)) + ".")
        gold = set(labels)
        output = analyze(row.get("document"))
        if output["summary"]["findings_truncated"]:
            raise ValueError("Статья превысила лимит результатов; неполный анализ нельзя включать в оценку.")
        # Only unquoted assertions enter the baseline's article-level decision.
        predicted = set(output["summary"]["by_category"])
        for key, score in counts.items():
            score["tp"] += int(key in gold and key in predicted)
            score["fp"] += int(key not in gold and key in predicted)
            score["fn"] += int(key in gold and key not in predicted)
            score["support"] += int(key in gold)
    if not seen:
        raise ValueError("Пустой корпус не позволяет оценить качество.")
    for score in counts.values():
        tp, fp, fn = score["tp"], score["fp"], score["fn"]
        score["precision"] = tp / (tp + fp) if tp + fp else None
        score["recall"] = tp / (tp + fn) if tp + fn else None
        score["f1"] = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"documents": len(seen), "unit": "document_category", "categories": counts,
            "note": "Оценка кандидатов needs_review против ручных меток; quoted_candidate и context_only исключены. Это не оценка границ фрагментов и не вероятность манипуляции."}

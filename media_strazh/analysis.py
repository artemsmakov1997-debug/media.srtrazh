"""Deterministic candidates for human review; no inference of intent or truth."""

from bisect import bisect_right
from collections import Counter
import hashlib
import json
import re

from .rules import RULES

VERSION = "rules-0.2.1"
MAX_CHARS = 200_000
MAX_FINDINGS = 500
CONTEXT_MARGIN = 200

# IDs correspond to the public methodology; coverage is deliberately explicit.
TAXONOMY = (
    ("fear", "Запугивание", True),
    ("emotional_evaluation", "Эмоциональная оценка", True),
    ("enemy_image", "Образ врага", True),
    ("exaggeration", "Преувеличение", True),
    ("generalization", "Обобщение", True),
    ("appeal_to_authority", "Ссылка на авторитет", False),
    ("vague_source", "Размытый источник", True),
    ("selective_context", "Выборочный контекст", False),
    ("oversimplification", "Упрощение", True),
    ("pseudostatistics", "Псевдостатистика", False),
    ("clickbait", "Кликбейт", True),
    ("euphemism_dysphemism", "Эвфемизмы и дисфемизмы", True),
)
LABELS = {key: label for key, label, _ in TAXONOMY}
SUPPORTED = {key for key, _, supported in TAXONOMY if supported}


COMPILED_RULES = [(rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in RULES]
TITLE_CERTAINTY = re.compile(r"\b(?:доказали|доказано|однозначно|безусловно|гарантированно)\b", re.I)
BODY_UNCERTAINTY = re.compile(
    r"\b(?:возможн[а-яё]*\s+связ[а-яё]*|предварительн[а-яё]*\s+(?:результат[а-яё]*|данн[а-яё]*)|"
    r"не\s+доказыва[а-яё]*\s+причинн[а-яё]*\s+связ[а-яё]*)\b", re.I,
)
POLITICAL_CONTEXT = re.compile(
    r"\b(?:(?:евро)?политик[а-яё]*|президент[а-яё]*|премьер[а-яё]*|министр[а-яё]*|"
    r"правительств[а-яё]*|власт[а-яё]*|режим[а-яё]*|лидер[а-яё]*|депутат[а-яё]*|"
    r"европ[а-яё]*|государств[а-яё]*|народ[а-яё]*|наци[а-яё]*|граждан[а-яё]*|ЕС)\b", re.I,
)
LITERAL_CLINICAL_CONTEXT = re.compile(
    r"\b(?:пациент[а-яё]*|врач[а-яё]*|больниц[а-яё]*|диагноз[а-яё]*|"
    r"лечени[а-яё]*|психиатрическ[а-яё]*|генетик[а-яё]*|заболевани[а-яё]*|"
    r"генетическ[а-яё]*\s+(?:нарушени[а-яё]*|отклонени[а-яё]*|мутаци[а-яё]*))\b", re.I,
)
LITERAL_ENTERTAINMENT_CONTEXT = re.compile(
    r"\b(?:фильм[а-яё]*|роман[а-яё]*|сериал[а-яё]*|акт[её]р[а-яё]*|"
    r"премьер[а-яё]*\s+фильм[а-яё]*|спектакл[а-яё]*|настольн[а-яё]*\s+игр[а-яё]*)\b", re.I,
)
LITERAL_ANIMAL_CONTEXT = re.compile(
    r"\b(?:биолог[а-яё]*|зоолог[а-яё]*|грызун[а-яё]*|насеком[а-яё]*|"
    r"дератизаци[а-яё]*|санэпид[а-яё]*|кишечник[а-яё]*|животн[а-яё]*)\b", re.I,
)
HUMAN_CONTEXT = re.compile(
    r"\b(?:народ[а-яё]*|населени[а-яё]*|граждан[а-яё]*|люд[а-яё]*|человек[а-яё]*|"
    r"солдат[а-яё]*|военн[а-яё]*|призывник[а-яё]*|нас|вас|их|мы)\b", re.I,
)
LIVESTOCK_CONTEXT = re.compile(r"\b(?:скот[а-яё]*|коров[а-яё]*|свин[а-яё]*|животн[а-яё]*|птиц[а-яё]*)\b", re.I)


def _rule_applies(rule, field, text, start, end):
    if field not in rule.fields:
        return False
    if not rule.context_requirement:
        return True
    sentence = _sentence(text, start, end)["text"]
    if rule.context_requirement == "human_violence":
        # A report on a slaughterhouse must not become a political metaphor.
        if LIVESTOCK_CONTEXT.search(sentence) and not HUMAN_CONTEXT.search(sentence):
            return False
        return bool(HUMAN_CONTEXT.search(sentence) or POLITICAL_CONTEXT.search(sentence))
    if rule.context_requirement == "political":
        if LITERAL_CLINICAL_CONTEXT.search(sentence) or LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
            return False
        if rule.id == "enemy.dehumanization" and LITERAL_ANIMAL_CONTEXT.search(sentence):
            return False
        # A pronoun or surname may refer to a target named in a preceding
        # paragraph. The bounded window never substitutes publisher identity.
        nearby = text[max(0, start - 900):min(len(text), end + 200)]
        return bool(POLITICAL_CONTEXT.search(nearby))
    raise ValueError("Неизвестное требование к контексту правила.")


def taxonomy():
    return [
        {"id": key, "label": label, "coverage": "candidate_rules" if supported else "not_evaluated"}
        for key, label, supported in TAXONOMY
    ]


def validate_document(document):
    if not isinstance(document, dict):
        raise ValueError("Ожидается JSON-объект с полями title и text.")
    unknown = set(document) - {"title", "text", "source", "url", "published_at"}
    if unknown:
        raise ValueError("Неизвестные поля документа: " + ", ".join(sorted(unknown)))
    for field in ("title", "text", "source", "url", "published_at"):
        if field in document and not isinstance(document[field], str):
            raise ValueError(f"Поле {field} должно быть строкой.")
    title, text = document.get("title", ""), document.get("text", "")
    if not text.strip():
        raise ValueError("Поле text должно содержать текст публикации.")
    if sum(len(value) for value in document.values()) > MAX_CHARS:
        raise ValueError(f"Документ превышает ограничение {MAX_CHARS} символов.")
    return title, text


def _quote_ranges(text):
    """Mark paired Russian, curly and ASCII double quotes, including nesting."""
    stack, ranges = [], []
    pairs = {"«": "»", "“": "”", "„": "“", '"': '"'}
    for index, char in enumerate(text):
        if stack and char == stack[-1][1]:
            start, _ = stack.pop()
            ranges.append((start, index + 1))
        elif char in pairs:
            stack.append((index, pairs[char]))
    # An unclosed quotation is treated cautiously, without inventing attribution.
    ranges.extend((start, len(text)) for start, _ in stack)
    merged = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _sentence(text, start, end):
    left = start
    while left > max(0, start - CONTEXT_MARGIN) and text[left - 1] not in ".!?\n":
        left -= 1
    right = end
    while right < min(len(text), end + CONTEXT_MARGIN) and text[right] not in ".!?\n":
        right += 1
    truncated = ((left > 0 and text[left - 1] not in ".!?\n") or
                 (right < len(text) and text[right] not in ".!?\n"))
    if right < len(text) and text[right] in ".!?\n":
        right += 1
    return {"start": left, "end": right, "text": text[left:right], "truncated": truncated}


def _evidence(field, text, start, end, quotes):
    sentence = _sentence(text, start, end)
    # Negation is local, not a semantic parse. A comma/colon breaks this scope.
    prefix = re.split(r"[,;:]", text[sentence["start"]:start])[-1][-60:]
    negated = bool(re.search(r"\bне\s+(?:(?!только\b)\w+\s+){0,2}$", prefix, re.I))
    discussed = bool(re.search(
        r'\b(?:слово|слова|выражение|фраза|формулировка|формулировку|термин|ярлык|тезис)\s*[:«"“„—-]?\s*$', prefix, re.I,
    ))
    denied = bool(re.search(
        r"\b(?:опроверг[а-яё]*|отверг[а-яё]*|неверно\s+(?:считать|утверждать)|нельзя\s+(?:считать|утверждать))\b",
        prefix, re.I,
    ))
    statement_prefix = text[sentence["start"]:start][-220:]
    reported = bool(re.search(
        r"\b(?:заявил[а-яё]*|сказал[а-яё]*|назвал[а-яё]*|утвержда[а-яё]*|отметил[а-яё]*|"
        r"считает|считают|по\s+словам)\b[^.!?\n]{0,110}$", statement_prefix, re.I,
    ) or re.search(
        r"^\s*(?:[»”\"]\s*)?[.,!?]?\s*[—-]\s*(?:так\s+)?(?:[^.!?\n]{0,45}\s+)?"
        r"(?:назвал[а-яё]*|заявил[а-яё]*|сказал[а-яё]*|отметил[а-яё]*)\b",
        text[end:min(len(text), end + 140)], re.I,
    ))
    quote_index = bisect_right(quotes, start, key=lambda interval: interval[0]) - 1
    quoted = quote_index >= 0 and end <= quotes[quote_index][1]
    context = {"in_quotes": quoted, "nearby_negation": negated or denied,
               "metalinguistic": discussed, "reported_speech": reported}
    return {"field": field, "start": start, "end": end, "quote": text[start:end],
            "sentence": sentence, "context": context}


def _status(evidence):
    context = evidence["context"]
    if context["nearby_negation"] or context["metalinguistic"]:
        return "context_only"
    if context["in_quotes"] or context.get("reported_speech"):
        return "quoted_candidate"
    return "needs_review"


def analyze(document):
    """Return exact spans relative to unchanged input, in Unicode code points."""
    title, text = validate_document(document)
    quotes = {"title": _quote_ranges(title), "text": _quote_ranges(text)}
    findings = []
    occupied = {}
    truncated = False
    for field, value in (("title", title), ("text", text)):
        for rule, pattern in COMPILED_RULES:
            if field not in rule.fields:
                continue
            for match in pattern.finditer(value):
                if not _rule_applies(rule, field, value, *match.span()):
                    continue
                spans = occupied.setdefault((field, rule.category), [])
                if any(match.start() < end and start < match.end() for start, end in spans):
                    continue
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    break
                evidence = _evidence(field, value, *match.span(), quotes[field])
                spans.append(match.span())
                findings.append({
                    "rule_id": rule.id, "category": rule.category, "label": LABELS[rule.category],
                    "status": _status(evidence), "explanation": rule.explanation,
                    "review_question": rule.review_question, "evidence": [evidence],
                })
    # Co-occurrence is a review cue, never proof that the claims contradict.
    caveat = BODY_UNCERTAINTY.search(text)
    if caveat:
        for certainty in TITLE_CERTAINTY.finditer(title):
            if len(findings) >= MAX_FINDINGS:
                truncated = True
                break
            heading = _evidence("title", title, *certainty.span(), quotes["title"])
            body = _evidence("text", text, *caveat.span(), quotes["text"])
            # Do not turn a quoted/negated caveat into an asserted limitation.
            if _status(body) != "needs_review":
                continue
            findings.append({
                "rule_id": "headline.certainty_gap", "category": "clickbait", "label": LABELS["clickbait"],
                "status": _status(heading),
                "explanation": "В заголовке есть категоричный вывод, а в тексте — оговорка о неопределённости. Связь между ними требует проверки.",
                "review_question": "Относятся ли вывод и оговорка к одному исследованию, субъекту и утверждению?",
                "evidence": [heading, body],
            })
    findings.sort(key=lambda f: (f["evidence"][0]["field"] != "title", f["evidence"][0]["start"], f["rule_id"]))
    for index, finding in enumerate(findings, 1):
        finding["id"] = f"f{index}"
    active = Counter(f["category"] for f in findings if f["status"] == "needs_review")
    digest = hashlib.sha256(json.dumps({"title": title, "text": text}, ensure_ascii=False,
                                      sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    warnings = [
        "Найденные признаки требуют проверки; они не доказывают манипуляцию, намерение автора или ложность фактов.",
        "Отсутствие признаков не означает нейтральность текста: охват правил ограничен.",
        "Кавычки, переданная речь и ближайшие отрицания распознаются эвристически; говорящий и дальние связи могут быть определены неверно.",
    ]
    if not re.search(r"[а-яё]", title + text, re.I):
        warnings.append("Русскоязычный текст не обнаружен; правила предназначены для русского языка.")
    if truncated:
        warnings.append(f"Результат ограничен {MAX_FINDINGS} совпадениями. Сводка неполная; разделите длинный текст на публикации.")
    return {
        "schema_version": "1.0", "algorithm_version": VERSION,
        "document": {"title": title, "text": text,
                     **{key: document[key] for key in ("source", "url", "published_at") if key in document},
                     "sha256": digest},
        "offset_unit": "unicode_code_points", "findings": findings,
        "summary": {"review_candidates": sum(active.values()), "by_category": dict(active),
                    "review_fragments": len({(e["field"], e["start"], e["end"])
                                             for f in findings if f["status"] == "needs_review"
                                             for e in f["evidence"]}),
                    "findings_truncated": truncated,
                    "quoted_candidates": sum(f["status"] == "quoted_candidate" for f in findings),
                    "context_only": sum(f["status"] == "context_only" for f in findings)},
        "coverage": taxonomy(), "warnings": warnings,
    }

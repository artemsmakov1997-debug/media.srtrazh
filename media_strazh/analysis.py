"""Deterministic candidates for human review; no inference of intent or truth."""

from bisect import bisect_right
from collections import Counter
import hashlib
import json
import re

from .rules import RULES

VERSION = "rules-0.4.0"
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
    ("appeal_to_authority", "Ссылка на авторитет", True),
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
    r"\b(?:(?:евро)?политик[а-яё]*|политическ[а-яё]*|президент[а-яё]*|премьер[а-яё]*|министр[а-яё]*|"
    r"правительств[а-яё]*|власт[а-яё]*|режим[а-яё]*|лидер[а-яё]*|депутат[а-яё]*|"
    r"оппозиц[а-яё]*|сенат[а-яё]*|конгресс[а-яё]*|губернатор[а-яё]*|мэр[а-яё]*|"
    r"европ[а-яё]*|государств[а-яё]*|стран[а-яё]*|(?:евро)?парламент[а-яё]*|народ[а-яё]*|наци[а-яё]*|граждан[а-яё]*|"
    r"украин[а-яё]*|росси[а-яё]*|беларус[а-яё]*|америк[а-яё]*|германи[а-яё]*|франци[а-яё]*|испан[а-яё]*|ЕС|США|"
    r"Трамп[а-яё]*|Путин[а-яё]*|Зеленск[а-яё]*|Макрон[а-яё]*|Байден[а-яё]*|Шольц[а-яё]*|Мерц[а-яё]*|Стармер[а-яё]*)\b", re.I,
)
MODERN_CUE = re.compile(
    r"\b(?:нынешн[а-яё]*|современн[а-яё]*|сегодня|сейчас|действующ[а-яё]*|"
    r"будущ[а-яё]*|станет|закончится|вернутся|правит|вед[её]т\s+себя|"
    r"Трамп[а-яё]*|Путин[а-яё]*|Зеленск[а-яё]*|Макрон[а-яё]*|Байден[а-яё]*|"
    r"Шольц[а-яё]*|Мерц[а-яё]*|Стармер[а-яё]*)\b", re.I,
)
CURRENT_TARGET = re.compile(
    r"\b(?:Трамп[а-яё]*|Путин[а-яё]*|Зеленск[а-яё]*|Макрон[а-яё]*|Байден[а-яё]*|"
    r"Шольц[а-яё]*|Мерц[а-яё]*|Стармер[а-яё]*|"
    r"(?:нынешн[а-яё]*|современн[а-яё]*|действующ[а-яё]*)\s+"
    r"(?:[а-яё]+\s+){0,2}(?:министр[а-яё]*|президент[а-яё]*|правительств[а-яё]*|"
    r"парламент[а-яё]*|политик[а-яё]*|власт[а-яё]*|росси[а-яё]*|украин[а-яё]*|Европ[а-яё]*))\b", re.I,
)
HISTORICAL_LITERAL = re.compile(
    r"\b(?:историк[а-яё]*|архив[а-яё]*|средневеков[а-яё]*|"
    r"(?:18\d\d|19[0-4]\d)\s*(?:-х|-е|год[а-яё]*|г\.)|"
    r"историческ[а-яё]*\s+(?:должност[а-яё]*|професси[а-яё]*))\b", re.I,
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
    r"дератизаци[а-яё]*|санэпид[а-яё]*|кишечник[а-яё]*|животн[а-яё]*|"
    r"собак[а-яё]*|псов|псы|пёс|псами|кошк[а-яё]*)\b", re.I,
)
HUMAN_CONTEXT = re.compile(
    r"\b(?:народ[а-яё]*|населени[а-яё]*|граждан[а-яё]*|люд[а-яё]*|человек[а-яё]*|"
    r"солдат[а-яё]*|военн[а-яё]*|призывник[а-яё]*|нас|вас|их|мы)\b", re.I,
)
LIVESTOCK_CONTEXT = re.compile(r"\b(?:скот[а-яё]*|коров[а-яё]*|свин[а-яё]*|животн[а-яё]*|птиц[а-яё]*)\b", re.I)

# Recognize attribution, not credibility. The same cue applies to all listed
# political speakers; their party, publisher and position never determine truth.
POLITICAL_SPEAKER_REPORT = re.compile(
    r"\b(?:(?:президент|премьер(?:-министр)?|министр|депутат|сенатор|лидер)"
    r"(?:\s+[а-яёa-z-]+){0,4}|Трамп|Путин|Зеленский|Макрон|Байден|Обама|"
    r"Шольц|Мерц|Стармер|Си\s+Цзиньпин)\s+"
    r"(?:(?:вновь|снова|резко|публично|также|сегодня|вчера|недавно)\s+){0,3}"
    r"(?:заявил[а-яё]*|сказал[а-яё]*|отметил[а-яё]*|подчеркнул[а-яё]*|"
    r"предложил[а-яё]*|призвал[а-яё]*|потребовал[а-яё]*|посоветовал[а-яё]*|"
    r"раскритиковал[а-яё]*|обрушился|считает)\b", re.I,
)
POLITICAL_PRESCRIPTION_TARGET = re.compile(
    r"\b(?:украин[а-яё]*|росси[а-яё]*|беларус[а-яё]*|кита[а-яё]*|"
    r"государств[а-яё]*|правительств[а-яё]*|стран[а-яё]*|власт[а-яё]*|"
    r"президент[а-яё]*|Зеленск[а-яё]*)\b", re.I,
)


def _rule_applies(rule, field, text, start, end, quotes=()):
    if field not in rule.fields:
        return False
    if not rule.context_requirement:
        return True
    sentence_span = _sentence(text, start, end)
    sentence = sentence_span["text"]
    if rule.context_requirement == "quote_omission":
        index = bisect_right(quotes, start, key=lambda interval: interval[0]) - 1
        return index >= 0 and end <= quotes[index][1]
    if rule.context_requirement in {"current_political", "modern_label", "modern_analogy",
                                    "political_machine", "political_collapse"}:
        nearby = text[max(0, start - 900):min(len(text), end + 200)]
        if not POLITICAL_CONTEXT.search(nearby) or LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
            return False
        modern = bool(MODERN_CUE.search(sentence))
        # Today's report about an archive is still about history. A time word
        # alone must not turn its historical subject into a current opponent.
        if HISTORICAL_LITERAL.search(sentence) and not (CURRENT_TARGET.search(sentence) or re.search(
            r"\b(?:будущ[а-яё]*|станет|закончится|вернутся)\b", sentence, re.I,
        )):
            return False
        if rule.context_requirement in {"modern_label", "modern_analogy"}:
            # Historical comparisons need a current target or a forecast in
            # the SAME sentence. Nearby political words alone are insufficient.
            prefix = text[sentence_span["start"]:start]
            # A current office/country may be named without a personal name.
            # Historical figures and explicit archival dates do not supply
            # this fallback. The candidate still needs semantic review.
            target = bool(POLITICAL_CONTEXT.search(prefix)) and not re.search(
                r"\b(?:Гитлер[а-яё]*|Муссолини|Сталин[а-яё]*|Черчилл[а-яё]*|"
                r"Чемберлен[а-яё]*|Рузвельт[а-яё]*|Наполеон[а-яё]*)\b", prefix, re.I,
            )
            if rule.id == "dysphemism.autocratic_label" and (re.match(
                r"\s+(?:Гитлер[а-яё]*|Муссолини|Сталин[а-яё]*|Наполеон[а-яё]*)\b",
                text[end:end + 40], re.I,
            ) or re.search(
                r"\b(?:Гитлер[а-яё]*|Муссолини|Сталин[а-яё]*|Наполеон[а-яё]*)\s*(?:[—:-]|это|был)?\s*$",
                prefix, re.I,
            )):
                return False
            if rule.context_requirement == "modern_analogy" and re.search(
                r"\b(?:рассказ[а-яё]*|описал[а-яё]*|объяснил[а-яё]*|изучил[а-яё]*)\b[^.!?\n]{0,60},\s*$",
                prefix, re.I,
            ):
                return False
            if rule.id == "enemy.nazi_political_label" and re.match(
                r"(?:нов[а-яё]*|современн[а-яё]*)\s+", text[start:end], re.I,
            ):
                return True
            return modern or target
        if rule.context_requirement == "political_machine":
            prefix = text[sentence_span["start"]:start]
            return bool(POLITICAL_CONTEXT.search(prefix)) and not re.search(
                r"\b(?:бронет[а-яё]*|танк[а-яё]*|гусениц[а-яё]*|двигател[а-яё]*|"
                r"завод[а-яё]*|техник[а-яё]*|автомобил[а-яё]*)\b", sentence, re.I,
            )
        if rule.context_requirement == "political_collapse":
            return not re.search(
                r"\b(?:здани[а-яё]*|кирпич[а-яё]*|фундамент[а-яё]*|мост[а-яё]*|"
                r"ветх[а-яё]*|крыша|кровл[а-яё]*)\b", sentence, re.I,
            )
        return True
    if rule.context_requirement == "prominent_authority_prescription":
        # A prominently selected prescriptive quote is a weak review cue, not
        # evidence that the newsroom adopted it or used status as proof.
        lead_end = text.find("\n")
        if field != "title" and start >= (lead_end if lead_end >= 0 else len(text)):
            return False
        speakers = list(POLITICAL_SPEAKER_REPORT.finditer(sentence))
        speakers = [match for match in speakers if not re.search(
            r"\b(?:компани[а-яё]*|банк[а-яё]*|клуб[а-яё]*|университет[а-яё]*)\b", match.group(), re.I)]
        if not speakers or not POLITICAL_PRESCRIPTION_TARGET.search(sentence):
            return False
        return not re.search(r"\b(?:футбол[а-яё]*|спортивн[а-яё]*|тренер[а-яё]*|капитан[а-яё]*)\b", sentence, re.I)
    if rule.context_requirement == "political_regime_label":
        # A geographic adjective plus "regime" can name a government through
        # a loaded label. An immediately specified operating/legal regime is
        # a different meaning, even when political words occur nearby.
        technical_tail = re.match(
            r"\s*(?:[«\"“„]\s*)?(?:работ[а-яё]*|движени[а-яё]*|"
            r"налогообложени[а-яё]*|налогов[а-яё]*|таможенн[а-яё]*|"
            r"визов[а-яё]*|безвизов[а-яё]*|пропускн[а-яё]*|пребывани[а-яё]*|"
            r"сна|питани[а-яё]*|лечени[а-яё]*|обучени[а-яё]*|"
            r"пол[её]т[а-яё]*|эксплуатаци[а-яё]*|освещени[а-яё]*|"
            r"энергосбережени[а-яё]*|тишины|подачи|экономии|доступа|"
            r"содержания|охраны|чрезвычайн[а-яё]*|военн[а-яё]*|карантин[а-яё]*)\b",
            text[end:end + 100], re.I,
        )
        return technical_tail is None
    if rule.context_requirement == "human_violence":
        # A report on a slaughterhouse must not become a political metaphor.
        if LIVESTOCK_CONTEXT.search(sentence) and not HUMAN_CONTEXT.search(sentence):
            return False
        return bool(HUMAN_CONTEXT.search(sentence) or POLITICAL_CONTEXT.search(sentence))
    if rule.context_requirement == "political":
        if LITERAL_CLINICAL_CONTEXT.search(sentence) or LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
            return False
        if rule.id in {"enemy.dehumanization", "enemy.group_animalization"} and LITERAL_ANIMAL_CONTEXT.search(sentence):
            return False
        if rule.id == "enemy.group_animalization":
            if re.search(r"\b(?:топлив[а-яё]*|сырь[а-яё]*|биоэнерг[а-яё]*|биотоплив[а-яё]*)\b", sentence, re.I):
                target_prefix = text[max(sentence_span["start"], start - 100):start]
                if not re.search(
                    r"\b(?:люди|солдат[а-яё]*|граждан[а-яё]*|работник[а-яё]*|бойц[а-яё]*|"
                    r"призывник[а-яё]*|населени[а-яё]*|народ[а-яё]*|журналист[а-яё]*|"
                    r"политик[а-яё]*|избирател[а-яё]*|оппонент[а-яё]*|чиновник[а-яё]*|"
                    r"беженц[а-яё]*)\s*(?:[—:-]\s*|(?:это|считают|рассматривают)\s*)$",
                    target_prefix, re.I,
                ):
                    return False
        # A pronoun or surname may refer to a target named in a preceding
        # paragraph. The bounded window never substitutes publisher identity.
        nearby = text[max(0, start - 900):min(len(text), end + 200)]
        return bool(POLITICAL_CONTEXT.search(nearby))
    if rule.context_requirement == "harm":
        return bool(re.search(
            r"\b(?:погиб[а-яё]*|смерт[а-яё]*|жертв[а-яё]*|ранен[а-яё]*|"
            r"убит[а-яё]*|пытк[а-яё]*|насили[а-яё]*)\b", sentence, re.I,
        ))
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
        r'\b(?:слово|слова|выражение|фраза|формулировка|формулировку|термин|ярлык|тезис|лозунг|слоган|клише|цитата|пример)\s*[:«"“„—-]?\s*$', prefix, re.I,
    ))
    denied = bool(re.search(
        r"\b(?:опроверг[а-яё]*|отверг[а-яё]*|неверно\s+(?:считать|утверждать)|нельзя\s+(?:считать|утверждать))\b",
        prefix, re.I,
    ))
    # An explicit rejected proposition may cross its complement comma. Other
    # commas still end local negation: "Не согласен, все знают" stays active.
    denied = denied or bool(re.search(
        r"\b(?:(?:нельзя|неверно|неправильно)\s+(?:считать|утверждать)|"
        r"(?:опроверг[а-яё]*|отверг[а-яё]*)\s+(?:утверждени[ея]|тезис|предположени[ея]|версию))"
        r"\s*,\s*(?:что|будто)\s+(?:[а-яё]+\s+){0,3}[«\"“„]?\s*$",
        text[sentence["start"]:start][-180:], re.I,
    ))
    statement_prefix = text[sentence["start"]:start][-220:]
    reported = bool(re.search(
        r"\b(?:заявил[а-яё]*|сказал[а-яё]*|назвал[а-яё]*|утвержда[а-яё]*|отметил[а-яё]*|"
        r"написал[а-яё]*|сообщил[а-яё]*|пояснил[а-яё]*|подчеркнул[а-яё]*|"
        r"считает|считают|по\s+(?:(?:его|её|ее|их|собственным)\s+)?(?:словам|мнению|убеждению))\b[^.!?\n]{0,110}$", statement_prefix, re.I,
    ) or re.search(
        r"^\s*(?:[»”\"]\s*)?[.!?]?\s*(?:[,—-]\s*|,\s*[—-]\s*)(?:так\s+)?"
        r"(?:(?!(?:но|однако|а|и)\b)[^.!?\n]{0,45}\s+)?"
        r"(?:назвал[а-яё]*|заявил[а-яё]*|сказал[а-яё]*|отметил[а-яё]*|подытожил[а-яё]*)\b",
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
                if not _rule_applies(rule, field, value, *match.span(), quotes[field]):
                    continue
                spans = occupied.setdefault((field, rule.category), [])
                if any(match.start() < end and start < match.end() for start, end in spans):
                    continue
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    break
                evidence = _evidence(field, value, *match.span(), quotes[field])
                if rule.id == "authority.prominent_prescriptive_quote":
                    # This rule requires attributed speech even without literal
                    # quotation marks. Denial/discussion still take priority.
                    evidence["context"]["reported_speech"] = True
                if rule.id == "context.quotation_omission":
                    # Editing is observable; distortion is not established.
                    evidence["context"]["quotation_edited"] = True
                spans.append(match.span())
                findings.append({
                    "rule_id": rule.id, "category": rule.category, "label": LABELS[rule.category],
                    "status": "context_only" if rule.id == "context.quotation_omission" else _status(evidence),
                    "explanation": rule.explanation,
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
                    "candidate_fragments": len({(e["field"], e["start"], e["end"])
                                                for f in findings if f["status"] != "context_only"
                                                for e in f["evidence"]}),
                    "findings_truncated": truncated,
                    "quoted_candidates": sum(f["status"] == "quoted_candidate" for f in findings),
                    "context_only": sum(f["status"] == "context_only" for f in findings)},
        "coverage": taxonomy(), "warnings": warnings,
    }

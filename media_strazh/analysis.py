"""Deterministic candidates for human review; no inference of intent or truth."""

from bisect import bisect_right
from collections import Counter
import hashlib
import json
import re

from .rules import HISTORICAL_JUXTAPOSITION, RULES

VERSION = "rules-0.11.0"
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
LABELS["event_terminology"] = "Выбор обозначения события"
LABELS["actor_terminology"] = "Обозначение участника"
LABELS["territory_terminology"] = "Обозначение территории"
LABELS["rhetorical_context"] = "Риторические сопоставления"
INFORMATIONAL = {"event_terminology", "actor_terminology", "territory_terminology", "rhetorical_context"}
SUPPORTED = {key for key, _, supported in TAXONOMY if supported}


COMPILED_RULES = [(rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in RULES
                  if rule.context_requirement not in {"historical_juxtaposition", "structural_notice"}]
STRUCTURAL_NOTICES = {rule.id: rule for rule in RULES if rule.context_requirement == "structural_notice"}
HISTORICAL_ANCHOR = re.compile(HISTORICAL_JUXTAPOSITION.pattern, re.I)
# A name/date alone is insufficient. The structural pass requires at least two
# recurring themes in a nearby current statement and a historical statement.
PARALLEL_THEMES = {
    "territory": ("территории и границы", re.compile(r"\b(?:территори|границ|земл|Судет|аннекси)[а-яё]*\b", re.I)),
    "historical_entitlement": ("историческая принадлежность или справедливость", re.compile(
        r"\bисторическ[а-яё]*\s+(?:Росси|родин|земл|территори|прав|справедливост)[а-яё]*\b", re.I)),
    "population_protection": ("защита населения", re.compile(
        r"\b(?:спас[а-яё]*|защит[а-яё]*|защищ[а-яё]*)\b.{0,65}\b(?:люд[а-яё]*|немц[а-яё]*|народ[а-яё]*|населени[а-яё]*|соотечественник[а-яё]*|граждан[а-яё]*)\b|"
        r"\b(?:люд[а-яё]*|немц[а-яё]*|народ[а-яё]*|населени[а-яё]*|соотечественник[а-яё]*|граждан[а-яё]*)\b.{0,65}\b(?:спас[а-яё]*|защит[а-яё]*|защищ[а-яё]*)\b|"
        r"\bпротив\s+(?:наших\s+людей|населени[а-яё]*|наш[а-яё]*\s+(?:граждан[а-яё]*|народ[а-яё]*))\b", re.I)),
    "security": ("угроза безопасности", re.compile(r"\b(?:угроз[а-яё]*|безопасност[а-яё]*)\b", re.I)),
    "national_unity": ("воссоединение народа", re.compile(
        r"\b(?:воссоединени[а-яё]*|(?:единств[а-яё]*|объединени[а-яё]*)\s+народ[а-яё]*)\b", re.I)),
}
PARALLEL_DISTANCE = 1800
PARALLEL_NEIGHBOURS = 5
REJECTED_PARALLEL = re.compile(
    r"\b(?:аналог[а-яё]*|сравнен[а-яё]*|сопоставлен[а-яё]*|параллел[а-яё]*)\b.{0,90}"
    r"\b(?:некорректн[а-яё]*|неуместн[а-яё]*|несостоятельн[а-яё]*|ошибочн[а-яё]*|не\s+доказыва[а-яё]*)\b|"
    r"\b(?:некорректн[а-яё]*|неуместн[а-яё]*|нельзя|не\s+следует)\b.{0,65}"
    r"\b(?:сравнива[а-яё]*|сопоставля[а-яё]*|аналог[а-яё]*|параллел[а-яё]*)\b|"
    r"\b(?:учебн[а-яё]*\s+пример|разбор\s+при[её]ма)\b.{0,65}\b(?:аналог[а-яё]*|сопоставлен[а-яё]*)\b", re.I,
)
HISTORICAL_SELECTION = re.compile(
    r"\b(?:(?:я\s+)?(?:решил[аи]?\s+(?:(?:ради\s+интереса|сегодня|снова)\s+)?|"
    r"(?:сегодня|сейчас|недавно)\s+)?(?:почитать|прочитать|перечитать|читаю|перечитал[аи]?|напомню))\b"
    r"[^.!?\n]{0,100}\b(?:речь|речи|выступлени[а-яё]*|цитат[а-яё]*|слов[а-яё]*)\b|"
    r"\b(?:ничего\s+не\s+напоминает|узна[её]те|найдите\s+отличия)\b", re.I,
)
HISTORICAL_STUDY = re.compile(
    r"\b(?:урок[а-яё]*|учебник[а-яё]*|историк[а-яё]*|архив[а-яё]*|музе[а-яё]*|"
    r"диссертаци[а-яё]*|источниковедени[а-яё]*|подлинност[а-яё]*|анализ\s+перевода)\b", re.I,
)
COMPARISON_LINK = re.compile(r"\b(?:при\s+этом|зато|тогда\s+как|а\s+вот|в\s+то\s+время\s+как|в\s+отличие|сравните)\b", re.I)
POSITIVE_POLE = re.compile(r"\b(?:счастлив[а-яё]*|благополучн[а-яё]*|богат[а-яё]*|процвета[а-яё]*|ухоженн[а-яё]*|красив[а-яё]*)\b", re.I)
NEGATIVE_POLE = re.compile(r"\b(?:несчастн[а-яё]*|депрессивн[а-яё]*|бедн[а-яё]*|нищ[а-яё]*|разрушенн[а-яё]*|заброшенн[а-яё]*|убог[а-яё]*)\b", re.I)
RANKING_CUE = re.compile(r"\b(?:рейтинг[а-яё]*|индекс[а-яё]*)\b", re.I)
PHOTO_WORD = r"(?:фото(?:графи[а-яё]*)?|снимк[а-яё]*|кадр[а-яё]*)"
FIRST_PHOTO = re.compile(r"\b(?:перв[а-яё]*|одн[а-яё]*)\s+" + PHOTO_WORD + r"\b", re.I)
SECOND_PHOTO = re.compile(r"\b(?:втор[а-яё]*|друг[а-яё]*)\s+" + PHOTO_WORD + r"\b", re.I)
PUBLIC_TARGET = re.compile(
    r"\b(?:стран[а-яё]*|государств[а-яё]*|город[а-яё]*|регион[а-яё]*|республик[а-яё]*|"
    r"Росси[а-яё]*|Украин[а-яё]*|Европ[а-яё]*|Финлянди[а-яё]*|Карели[а-яё]*|"
    r"СССР|советск[а-яё]*|совок|совк[а-яё]*|Запад[а-яё]*|власт[а-яё]*|режим[а-яё]*|"
    r"либерал[а-яё]*|коммунист[а-яё]*|консерватор[а-яё]*|националист[а-яё]*|политик[а-яё]*)\b", re.I,
)
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
    r"собак[а-яё]*|псов|псы|пёс|псами|кошк[а-яё]*|птиц[а-яё]*|пингвин[а-яё]*|волк[а-яё]*)\b", re.I,
)
HUMAN_CONTEXT = re.compile(
    r"\b(?:народ[а-яё]*|населени[а-яё]*|граждан[а-яё]*|люд[а-яё]*|человек[а-яё]*|"
    r"солдат[а-яё]*|военн[а-яё]*|призывник[а-яё]*|нас|вас|их|мы)\b", re.I,
)
LIVESTOCK_CONTEXT = re.compile(r"\b(?:скот[а-яё]*|коров[а-яё]*|свин[а-яё]*|животн[а-яё]*|птиц[а-яё]*)\b", re.I)

# These bounded cues ask for the basis of a quantity claim. They do not decide
# whether the claim is true or whether evidence exists elsewhere in a document.
GROUP_ASSERTION = re.compile(
    r"\b(?:утвержда[а-яё]*|сообща[а-яё]*|говор[а-яё]*|счита[а-яё]*|поддержива[а-яё]*|"
    r"одобря[а-яё]*|выступа[а-яё]*|отказ[а-яё]*|заявля[а-яё]*|опаса[а-яё]*|"
    r"верят|верили|голос[а-яё]*|соверша[а-яё]*|совершили|принима[а-яё]*|принимали|"
    r"получа[а-яё]*|получили|хотят|готовы|столкнулись)\b", re.I,
)
PUBLIC_EVENT = re.compile(
    r"\b(?:задержанн[а-яё]*|обвиняем[а-яё]*|подозреваем[а-яё]*|несовершеннолетн[а-яё]*|"
    r"граждан[а-яё]*|жител[а-яё]*|преступлени[а-яё]*|поджог[а-яё]*|диверси[а-яё]*|"
    r"терроризм[а-яё]*|суд[а-яё]*|компани[а-яё]*|предприяти[а-яё]*|избирател[а-яё]*)\b", re.I,
)
EVENT_ASSERTION = re.compile(
    r"\b(?:задержива[а-яё]*|задержали|возбужда[а-яё]*|возбудили|обвиня[а-яё]*|"
    r"обвинили|арестовыва[а-яё]*|арестовали|соверша[а-яё]*|совершили|"
    r"осужда[а-яё]*|осудили|привлека[а-яё]*|привлекли|отказыва[а-яё]*|отказали|"
    r"голосуют|голосовали|закрыва[а-яё]*|закрыли|увольня[а-яё]*|уволили)\b", re.I,
)
COUNT_CONTEXT = re.compile(
    r"\b(?:числ[а-яё]*|количеств[а-яё]*|доля|доли|долю|долей|доле|"
    r"частот[а-яё]*|процент[а-яё]*|случа[а-яё]*|поджог[а-яё]*|"
    r"задержани[а-яё]*|преступлени[а-яё]*|нарушени[а-яё]*)\b", re.I,
)
DIRECT_QUANTITY = re.compile(
    r"\s*\(\s*(?:в\s+)?\d+(?:[.,]\d+)?\s*"
    r"(?:%|процент[а-яё]*|из\s+\d+(?:\s+[а-яё]+){0,2})\s*\)", re.I,
)
DIRECT_DIFFERENCE = re.compile(
    r"\s*(?:[—–:,-]\s*|\(\s*)?(?:(?:на|в)\s+\d+(?:[.,]\d+)?\s*"
    r"(?:%|процент[а-яё]*|раз[а-яё]*)|\d+(?:[.,]\d+)?\s*%|\d+\s+против\s+\d+)(?!\w)", re.I,
)
CLAUSE_QUANTITY = re.compile(
    r"^[^,;.!?\n]{0,100}[:(]\s*(?:в\s+)?\d+(?:[.,]\d+)?\s*"
    r"(?:%|процент[а-яё]*|из\s+\d+\b)", re.I,
)
WAR_PARTICIPANT = re.compile(r"\b(?:украин[а-яё]*|росси[а-яё]*|киев[а-яё]*|Путин[а-яё]*|Зеленск[а-яё]*)\b", re.I)
WAR_ACTION = re.compile(
    r"\b(?:войн[а-яё]*|вторжени[а-яё]*|военн[а-яё]*|боев[а-яё]*|фронт[а-яё]*|"
    r"ветеран[а-яё]*|мобилиз[а-яё]*|военнослужащ[а-яё]*|вооруж[а-яё]*|"
    r"солдат[а-яё]*|погиб[а-яё]*|участник[а-яё]*)\b", re.I,
)
OTHER_WAR_CONTEXT = re.compile(
    r"\b(?:втор[а-яё]*\s+миров[а-яё]*|велик[а-яё]*\s+отечественн[а-яё]*|"
    r"1939|1941|1945|Ирак[а-яё]*|Афганистан[а-яё]*|Сири[а-яё]*|Ливан[а-яё]*|"
    r"Газ[аеуы]|Израил[а-яё]*)\b", re.I,
)
OTHER_SVO = re.compile(
    r"\b(?:систем[а-яё]*\s+(?:водян[а-яё]*|воздушн[а-яё]*)\s+охлаждени[а-яё]*|"
    r"охлаждени[а-яё]*|радиатор[а-яё]*|процессор[а-яё]*|"
    r"совет\s+ветеранов\s+организации)\b", re.I,
)

# Require a nearby grammatical link to a territory, not simply a place name
# somewhere in a political report. This explicit vocabulary is not a geocoder.
TERRITORY_REFERENCE = (
    r"(?:территори(?:я|и|ю|ей|ею|ям|ями|ях)|"
    r"город(?:а|у|ом|е|ов|ам|ами|ах)?|"
    r"с[её]л(?:о|а|у|ом|е|ам|ами|ах)|сёл|деревн(?:я|и|ю|е|ей|ям|ями|ях)|"
    r"пос[её]л(?:ок|ка|ку|ком|ке|ки|ков|кам|ками|ках)|"
    r"насел[её]нн[а-яё]*\s+пункт(?:а|у|ом|е|ы|ов|ам|ами|ах)?|"
    r"район(?:а|у|ом|е|ы|ов|ам|ами|ах)?|"
    r"област(?:ь|и|ью|ей|ям|ями|ях)|регион(?:а|у|ом|е|ы|ов|ам|ами|ах)?|"
    r"(?:полу)?остров(?:а|у|ом|е|ов|ам|ами|ах)?|"
    r"республик(?:а|и|у|е|ой|ам|ами|ах)|стран(?:а|ы|у|е|ой|ам|ами|ах)|"
    r"земл(?:я|и|ю|е|ей|ям|ями|ях)|провинци(?:я|и|ю|ей|ям|ями|ях)|"
    r"Крым(?:а|у|ом|е)?|Донбасс(?:а|у|ом|е)?|"
    r"(?:Донецк|Луганск|Херсон|Бахмут)(?:а|у|ом|е)?|"
    r"Мариупол(?:ь|я|ю|ем|е)|"
    r"(?:О|А)л[её]ш(?:ки|ек|кам|ками|ках)|"
    r"Севастопол(?:ь|я|ю|ем|е)|Запорожь(?:е|я|ю|ем)|"
    r"Украин(?:а|ы|е|у|ой)|Росси(?:я|и|ю|ей)|"
    r"Палестин(?:а|ы|е|у|ой)|Газ(?:а|ы|е|у|ой)|"
    r"Судет(?:ы|ов|ам|ами|ах)|Карабах(?:а|у|ом|е)?|"
    r"Голанск[а-яё]*\s+высот[а-яё]*|Западн[а-яё]*\s+берег[а-яё]*)"
)
TERRITORY_ADJECTIVE = r"[а-яё-]{1,35}(?:ый|ий|ая|ое|ее|ие|ые|ого|его|ому|ему|ой|ей|ую|юю|ым|им|ых|их|ыми|ими|ом|ем)"
TERRITORY_AGENT = (r"(?:(?:" + TERRITORY_ADJECTIVE + r"\s+){0,2}"
                   r"(?:войсками|силами|армией|военными)|Россией|Украиной|ВСУ|ВС\s+РФ)")
TERRITORY_LEADING_AGENT = re.compile(r"^\s*[«»\"“”]?\s*" + TERRITORY_AGENT + r"\b", re.I)
TERRITORY_AFTER = re.compile(
    r"^\s*[«»\"“”]?\s*"
    r"(?P<modifiers>(?:" + TERRITORY_ADJECTIVE + r"\s+){0,3})"
    r"\b" + TERRITORY_REFERENCE + r"\b", re.I,
)
TERRITORY_BEFORE = re.compile(
    r"\b" + TERRITORY_REFERENCE + r"\b"
    r"(?P<modifiers>(?:\s+(?:" + TERRITORY_ADJECTIVE + r"|(?-i:[А-ЯЁ][а-яё-]{1,35}))){0,3})"
    r"\s*[»\"”]?\s*,?\s*(?:(?:который|которая|которое|которые|был|была|было|были|будет|будут|"
    r"считается|считаются|назван|названа|названо|названы|признан|признана|признано|признаны|"
    r"называют|назвали|считают|считали|"
    r"ранее|вновь|недавно|полностью|якобы|временно|частично|снова|теперь|уже|не)\s+){0,4}"
    r"[«\"“]?\s*$", re.I,
)
NON_TERRITORY_MODIFIER = re.compile(
    r"\b(?:заключ[её]нн[а-яё]*|пленн[а-яё]*|задержанн[а-яё]*|"
    r"осужд[её]нн[а-яё]*|арестованн[а-яё]*|военнослужащ[а-яё]*)\b", re.I,
)
NON_TERRITORY_AFTER = re.compile(
    r"^\s*[»\"”]?\s*(?:(?:" + TERRITORY_ADJECTIVE + r")\s+){0,2}"
    r"(?:заключ[её]нн[а-яё]*|пленн[а-яё]*|задержанн[а-яё]*|осужд[её]нн[а-яё]*|"
    r"арестованн[а-яё]*|военнослужащ[а-яё]*|заложник[а-яё]*|человек[а-яё]*|"
    r"жител[а-яё]*|сотрудник[а-яё]*|пациент[а-яё]*|мест[а-яё]*|врем[а-яё]*|"
    r"(?:из\s+(?:плена|тюрьм[а-яё]*|колони[а-яё]*))|под\s+залог)\b", re.I,
)
LITERAL_RELEASE = re.compile(
    r"^\s+от\s+(?:уплат[а-яё]*\s+)?(?:налог[а-яё]*|долг[а-яё]*|пошлин[а-яё]*|"
    r"плат[а-яё]*|обязанност[а-яё]*|ответственност[а-яё]*|наказани[а-яё]*|"
    r"работ[а-яё]*|должност[а-яё]*|снег[а-яё]*|льда|мусор[а-яё]*|завал[а-яё]*)\b", re.I,
)


def _territory_term_context(rule, text, start, end, sentence_span):
    """Match a bounded noun phrase/predicate; preserve only the term as evidence."""
    left = text[max(sentence_span["start"], start - 160):start]
    right = text[end:min(sentence_span["end"], end + 160)]
    # Consume an explicit agent once. Regex backtracking must not reinterpret
    # «Россией» in «освобождённый Россией солдат» as the territory itself.
    agent = TERRITORY_LEADING_AGENT.match(right)
    if agent:
        right = right[agent.end():]
    if NON_TERRITORY_AFTER.match(right):
        return False
    if rule.id == "terminology.liberated_territory" and LITERAL_RELEASE.match(right):
        return False
    after = TERRITORY_AFTER.search(right)
    if after and not NON_TERRITORY_MODIFIER.search(after["modifiers"]):
        return True
    before = TERRITORY_BEFORE.search(left)
    if not before or NON_TERRITORY_MODIFIER.search(before["modifiers"]):
        return False
    # «В Крыму освобождён ...» gives a location, not the object of release.
    preposition = re.search(r"\b(?:в|во|на|из|к|ко|с|со|у|о|об|от|для|по)\s+$", left[:before.start()], re.I)
    return not preposition or "," in left[before.start():]

# Recognize attribution, not credibility. The same cue applies to all listed
# political speakers; their party, publisher and position never determine truth.
POLITICAL_SPEAKER_REPORT = re.compile(
    r"\b(?:(?:президент|премьер(?:-министр)?|министр|депутат|сенатор|лидер|политик)"
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

# These restrictions distinguish a human-targeted metaphor from a literal
# discussion of props, pests or ownership. The attack words themselves are not
# literal-context exclusions, unlike an undifferentiated animal word list.
LITERAL_ATTACK_CONTEXT = re.compile(
    r"\b(?:биолог[а-яё]*|зоолог[а-яё]*|энтомолог[а-яё]*|паразитолог[а-яё]*|"
    r"ветеринар[а-яё]*|дератизаци[а-яё]*|дезинсекци[а-яё]*|инсектицид[а-яё]*|"
    r"помещени[а-яё]*|подвал[а-яё]*|квартир[а-яё]*|посев[а-яё]*|волос[а-яё]*|"
    r"педикул[а-яё]*|ветклиник[а-яё]*|приют[а-яё]*|зоопарк[а-яё]*|"
    r"собак[а-яё]*|щен[а-яё]*|кошк[а-яё]*|кот(?:а|у|ом|е|ы|ов|ам|ами|ах)?|"
    r"врач[а-яё]*|лечени[а-яё]*|пациент[а-яё]*|"
    r"металлург[а-яё]*|топлив[а-яё]*|коксохим[а-яё]*|литейн[а-яё]*)\b", re.I,
)
PERSON_REFERENCE = r"(?:президент[а-яё]*|политик[а-яё]*|депутат[а-яё]*|министр[а-яё]*|люд[а-яё]*|граждан[а-яё]*|оппонент[а-яё]*)"
POLITICAL_ACTOR = (
    r"(?:" + PERSON_REFERENCE + r"|человек[а-яё]*|чиновник[а-яё]*|лидер[а-яё]*|"
    r"правительств[а-яё]*|власт[а-яё]*|режим[а-яё]*|оппозиц[а-яё]*|сенат[а-яё]*|"
    r"конгресс[а-яё]*|губернатор[а-яё]*|мэр[а-яё]*|(?:евро)?парламент[а-яё]*|"
    r"Трамп[а-яё]*|Путин[а-яё]*|Зеленск[а-яё]*|Макрон[а-яё]*|Байден[а-яё]*|"
    r"Шольц[а-яё]*|Мерц[а-яё]*|Стармер[а-яё]*)"
)
POLITICAL_ACTOR_CONTEXT = re.compile(r"\b" + POLITICAL_ACTOR + r"\b", re.I)
LITERAL_PEST_CONTEXT = re.compile(
    r"\b(?:клоп[а-яё]*|блох[а-яё]*|таракан[а-яё]*|комар[а-яё]*|личинк[а-яё]*|"
    r"гостиниц[а-яё]*|гостиничн[а-яё]*\s+номер[а-яё]*|депо|метрополитен[а-яё]*)\b", re.I,
)
LITERAL_PEST_ACTIVITY = re.compile(
    r"\b(?:насеком[а-яё]*|беспозвоночн[а-яё]*|членистоног[а-яё]*)\s*,?\s*"
    r"(?:обита[а-яё]*|живут|размножа[а-яё]*|опыля[а-яё]*|собран[а-яё]*|нов[а-яё]*\s+вид[а-яё]*)\b|"
    r"\b(?:принести|прин[её]с[а-яё]*|занести|зан[её]с[а-яё]*)\b[^.!?\n]{0,80}"
    r"\bнасеком[а-яё]*\b[^.!?\n]{0,40}\bдомой\b", re.I,
)

# Personal labels require a political target, not just a country elsewhere in
# the article. Names are an explicit, non-exhaustive list; roles cover others.
POLITICAL_PERSON_ROLE = r"(?:президент|премьер(?:-министр)?|министр|депутат|сенатор|политик|оппозиционер|канцлер|губернатор|мэр|лидер)"
POLITICAL_PERSON_NOM = (r"(?:" + POLITICAL_PERSON_ROLE + r"|Путин|Зеленский|Трамп|Байден|Макрон|Мерц|"
                        r"Шольц|Стармер|Медведев|Лукашенко)")
POLITICAL_PERSON = (r"(?:" + POLITICAL_PERSON_ROLE + r"(?:а|у|ом|е|ы|ов|ам|ами|ах)?|политики|"
                    r"(?:Путин|Трамп|Байден|Макрон|Мерц|Шольц|Стармер|Медведев)(?:а|у|ом|ым|е)?|"
                    r"Зеленск(?:ий|ого|ому|им|ом)|Лукашенко)")
POLITICAL_PERSON_CONTEXT = re.compile(r"\b" + POLITICAL_PERSON + r"\b", re.I)
LABEL_MODIFIER = r"(?:настоящ[а-яё]*|жалк[а-яё]*|обычн[а-яё]*|обыкновенн[а-яё]*|кровав[а-яё]*|кровожадн[а-яё]*|политическ[а-яё]*|просто|вновь|снова|действительно)"
LITERAL_PERFORMER_ROLE = re.compile(
    r"\b(?:играл[а-яё]*|сыграл[а-яё]*|исполнил[а-яё]*)\s+(?:роль\s+)?(?:[а-яё-]+\s+){0,2}$|"
    r"\b(?:работает|работал[а-яё]*|професси[а-яё]*|роль|роли)\s*(?:[а-яё-]+\s+){0,2}$", re.I,
)
LITERAL_PERFORMER_TAIL = re.compile(
    r"^\s*[»\"”]?\s*(?:по\s+профессии|(?:в|на)\s+(?:[а-яё-]+\s+){0,2}"
    r"(?:цирк[а-яё]*|арен[а-яё]*|спектакл[а-яё]*|фильм[а-яё]*|постановк[а-яё]*))\b", re.I,
)
LEGAL_PERSON_REPORT = re.compile(
    r"\b(?:суд[а-яё]*|присяжн[а-яё]*)\b[^.!?;\n]{0,90}"
    r"\b(?:признал[а-яё]*|установил[а-яё]*|постановил[а-яё]*|осудил[а-яё]*|приговорил[а-яё]*)\b|"
    r"\b(?:признал[а-яё]*|установил[а-яё]*|постановил[а-яё]*|осудил[а-яё]*)\b"
    r"[^.!?;\n]{0,60}\b(?:суд[а-яё]*|присяжн[а-яё]*)\b", re.I,
)


def _political_person_label(rule, text, start, end, sentence_span, event_context):
    prefix = text[max(sentence_span["start"], start - 140):start]
    suffix = text[end:min(sentence_span["end"], end + 140)]
    sentence = sentence_span["text"]
    if HISTORICAL_LITERAL.search(sentence) and not CURRENT_TARGET.search(sentence):
        return False
    if rule.id == "dysphemism.performer_label":
        if LITERAL_PERFORMER_ROLE.search(prefix) or LITERAL_PERFORMER_TAIL.match(suffix):
            return False
    if rule.id == "dysphemism.murderer_label":
        if LEGAL_PERSON_REPORT.search(prefix) or re.match(
            r"^\s*[»\"”]?\s*[,—-]\s*(?:признал[а-яё]*|установил[а-яё]*|постановил[а-яё]*|осудил[а-яё]*)"
            r"\s+(?:суд[а-яё]*|присяжн[а-яё]*)\b", suffix, re.I,
        ) or re.search(
            r"\b(?:прокурор[а-яё]*|следовател[а-яё]*)\b[^.!?;\n]{0,90}\bназвал[а-яё]*\b", prefix, re.I,
        ):
            return False
    if rule.id == "dysphemism.bloody_epithet" and re.match(
        r"^\s*(?:после|из-за|от)\s+(?:(?:тяж[её]л[а-яё]*|полученн[а-яё]*)\s+)?"
        r"(?:ранени[а-яё]*|ран[а-яё]*|травм[а-яё]*)\b", suffix, re.I,
    ):
        return False
    if rule.id == "dysphemism.bloody_epithet" and re.fullmatch(
        r"(?:кровав|кровожадн)(?:ая|ую|ой)", text[start:end], re.I,
    ) and re.match(r"^\s+(?:(?:внешн|внутренн)[а-яё]*\s+)?политик(?:а|у|е|ой|и)\b", suffix, re.I):
        return False
    names = r"(?:\s+(?-i:[А-ЯЁ][а-яё-]{1,30})){0,3}"
    label_chain = (r"(?:(?:" + LABEL_MODIFIER + r"\s+){0,2}"
                   r"(?:клоун|паяц|скоморох|шут|диктатор|тиран|убийц|кровав|кровожадн)[а-яё]*"
                   r"\s*(?:,\s*(?:а\s+)?|и\s+)){0,3}")
    # Direct predicate/apposition: «Путин — клоун», «Зеленского назвали клоуном».
    direct = re.search(
        r"\b" + POLITICAL_PERSON + names +
        r"\s*(?:[—,:-]\s*|(?:это|был|была|назвали|называют|считают)\s+)?"
        r"(?:не\s+)?" + label_chain + r"(?:не\s+)?(?:" + LABEL_MODIFIER + r"\s+){0,2}[«\"“]?\s*$", prefix, re.I,
    )
    # A noun followed by a genitive may name the victim («убийца президента»).
    # Require nominative apposition here; other cases remain covered by naming.
    person_after = POLITICAL_PERSON if rule.id == "dysphemism.bloody_epithet" else POLITICAL_PERSON_NOM
    descriptor = r"(?:(?:диктатор|тиран|убийц|клоун)[а-яё]*\s+)?" if rule.id == "dysphemism.bloody_epithet" else ""
    forward = re.match(r"^\s*[»\"”]?\s*" + descriptor + r"(?:(?-i:[А-ЯЁ][а-яё-]{1,30})\s+){0,2}"
                       r"\b" + person_after + r"\b", suffix, re.I)
    reverse = re.match(r"^\s*[»\"”]?\s+(?:назвали|называют|считают)\s+"
                       r"(?:(?-i:[А-ЯЁ][а-яё-]{1,30})\s+){0,2}" + POLITICAL_PERSON + r"\b", suffix, re.I)
    if direct or forward or reverse:
        return True
    if POLITICAL_PERSON_CONTEXT.search(sentence) and re.search(
        r"\b(?:слово|ярлык|прозвище|обозначение)\s*[«\"“]?\s*$", prefix, re.I,
    ):
        return True
    # Bounded nickname resolution, deliberately excluded for a criminal noun.
    if rule.id == "dysphemism.murderer_label":
        return False
    left = max(text.rfind("\n", 0, sentence_span["start"]) + 1, start - 200)
    previous = text[left:sentence_span["start"]] + "\n" + event_context[:350]
    if not POLITICAL_PERSON_CONTEXT.search(previous):
        return False
    if LITERAL_ENTERTAINMENT_CONTEXT.search(sentence + "\n" + previous) or re.search(
        r"\b(?:цирк[а-яё]*|арен[а-яё]*|професси[а-яё]*)\b", sentence + "\n" + previous, re.I,
    ):
        return False
    return bool((not prefix.strip() and not suffix.strip(" .!?\n\t")) or re.match(
        r"^\s*(?:(?:вновь|снова|уже|не|теперь)\s+){0,2}(?:заявил[а-яё]*|заявля[а-яё]*|"
        r"потребовал[а-яё]*|требует|призвал[а-яё]*|призыва[а-яё]*|подписал[а-яё]*|"
        r"отказал[а-яё]*|хочет|(?:диктатор|тиран)(?:а|у|ом|е|ы|ов|ам|ами|ах)?)\b", suffix, re.I,
    ))


def _direct_person_metaphor(text, start, end, sentence_span):
    """A nearby official alone is not the target of every noun in the report."""
    prefix = text[max(sentence_span["start"], start - 140):start]
    suffix = text[end:min(len(text), end + 140)]
    names = r"(?:\s+(?-i:[А-ЯЁ][а-яё-]+)){0,2}"
    copula = (r"\b" + POLITICAL_ACTOR + names +
              r"\s*(?:[—-]|это|назвали|называют|считают|(?=не\s))\s*(?:не\s+)?[«\"“]?\s*$")
    naming = (r"\b(?:назва[а-яё]*|называ[а-яё]*|счита[а-яё]*)\s+"
              r"(?:[а-яё-]+\s+){0,2}" + POLITICAL_ACTOR + names + r"\s*[«\"“]?\s*$")
    reverse = (r"^\s*[»\"”]?\s+(?:назва[а-яё]*|называ[а-яё]*|счита[а-яё]*)\s+"
               r"(?:[а-яё-]+\s+){0,2}" + POLITICAL_ACTOR + r"\b")
    return bool(re.search(copula, prefix, re.I) or re.search(naming, prefix, re.I)
                or re.search(reverse, suffix, re.I))


def _psychological_label_context(text, start, end, sentence_span, event_context):
    sentence = sentence_span["text"]
    if LITERAL_CLINICAL_CONTEXT.search(sentence) or LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
        return False
    if re.match(r"истерик", text[start:end], re.I):
        prefix = text[max(sentence_span["start"], start - 100):start]
        # Reported distress, including inside quotes, is not a political label.
        # This does not suppress the evaluative phrase «закатил истерику».
        if re.search(
            r"\b(?:начал[а-яё]*|случил[а-яё]*|возник[а-яё]*|произош[а-яё]*|пережи[а-яё]*|"
            r"испытыва[а-яё]*|страда[а-яё]*\s+от|приступ[а-яё]*|"
            r"впал[а-яё]*\s+в|дов[её]л[а-яё]*\s+до)\s+(?:[а-яё-]+\s+){0,3}$|"
            r"\bу\s+(?:[а-яё-]+\s+){1,4}$", prefix, re.I,
        ):
            return False
    if POLITICAL_ACTOR_CONTEXT.search(sentence):
        return True
    # Resolve only a nearby pronoun in this paragraph or the paired field;
    # geography or an unrelated party name elsewhere cannot supply a target.
    paragraph_start = max(text.rfind("\n", 0, sentence_span["start"]) + 1,
                          sentence_span["start"] - 200)
    previous = text[paragraph_start:sentence_span["start"]] + "\n" + event_context
    return bool(re.search(r"\b(?:он|она|они|его|её|ее|их)\b", sentence, re.I)
                and POLITICAL_ACTOR_CONTEXT.search(previous))


def _human_attack_context(text, start, end, sentence_span, event_context, require_actor=False):
    sentence = sentence_span["text"]
    if LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
        return False
    nearby = text[max(0, start - 900):min(len(text), end + 200)] + "\n" + event_context
    if require_actor:
        direct = _direct_person_metaphor(text, start, end, sentence_span)
    else:
        prefix = text[max(sentence_span["start"], start - 100):start]
        direct = bool(re.search(r"\b" + PERSON_REFERENCE + r"\s*(?:[—:-]|это|назвали|называют|считают)\s*$", prefix, re.I))
    paragraph_start = max(text.rfind("\n", 0, start) + 1, start - 400)
    literal_scope = text[paragraph_start:sentence_span["start"] + len(sentence)]
    if LITERAL_ATTACK_CONTEXT.search(literal_scope) and not direct:
        return False
    if require_actor:
        if (LITERAL_PEST_CONTEXT.search(literal_scope) or LITERAL_PEST_ACTIVITY.search(sentence)) and not direct:
            return False
        if direct:
            return True
        if not POLITICAL_ACTOR_CONTEXT.search(nearby):
            return False
        # For biological nouns, an official in the same report still does not
        # establish a human target. Require a derogatory modifier or human
        # behaviour attached to the noun. «Тварь»/«суетливое существо» retain
        # their separate, ambiguous personal-insult reading after literal guards.
        phrase = text[start:end]
        if re.search(r"\b(?:твар[а-яё]*|суетлив[а-яё]*|киевск[а-яё]*|наркотическ[а-яё]*|тифозн[а-яё]*)\b", phrase, re.I):
            return True
        tail = text[end:sentence_span["start"] + len(sentence)]
        return bool(re.match(
            r"\s*(?:(?:вновь|снова|уже|теперь|якобы)\s+){0,2}"
            r"(?:уговарива[а-яё]*|обсужда[а-яё]*|заявля[а-яё]*|призыва[а-яё]*|"
            r"проголосова[а-яё]*|правят|лгут|труслив[а-яё]*)\b", tail, re.I,
        ))
    return direct or bool(POLITICAL_CONTEXT.search(nearby))


def _rule_applies(rule, field, text, start, end, quotes=(), event_context=""):
    if field not in rule.fields:
        return False
    if not rule.context_requirement:
        return True
    sentence_span = _sentence(text, start, end)
    sentence = sentence_span["text"]
    if rule.context_requirement == "degrading_place":
        nearby = text[max(0, start - 250):end]
        literal = re.search(r"\b(?:мусор[а-яё]*|отход[а-яё]*|контейнер[а-яё]*|вывоз[а-яё]*|уборк[а-яё]*|свалк[а-яё]*)\b", sentence, re.I)
        return bool(PUBLIC_TARGET.search(nearby + " " + event_context)) and not literal
    if rule.context_requirement == "sovok_label":
        literal = re.search(r"\b(?:веник[а-яё]*|щ[её]тк[а-яё]*|уборк[а-яё]*|мусор[а-яё]*|совоч[а-яё]*|песочниц[а-яё]*|лопат[а-яё]*|инструмент[а-яё]*|"
                            r"купил[а-яё]*|покупа[а-яё]*|прода[а-яё]*|лежит|лежал[а-яё]*|ручк[а-яё]*|пластмассов[а-яё]*|пластиков[а-яё]*|металлическ[а-яё]*)\b", sentence, re.I)
        # The matched word itself cannot supply its own political context.
        surrounding = text[max(0, start - 300):start] + " " + text[end:min(len(text), end + 120)]
        return not literal and bool(PUBLIC_TARGET.search(surrounding + " " + event_context) or re.search(r"\bсуть\s*$", text[max(0, start - 25):start], re.I))
    if rule.context_requirement == "political_essence":
        target = re.match(r"\s+(?:(?:этого|этой|нашего|нынешнего|современного)\s+)?([а-яё]+)\b", text[end:end + 90], re.I)
        return bool(target and PUBLIC_TARGET.fullmatch(target[1]))
    if rule.context_requirement == "impersonal_political_opinion":
        prefix = text[max(sentence_span["start"], start - 120):start]
        attributed = re.search(r"\b(?:мне|нам|ему|ей|им|экспертам|исследователям)\s*$|\b(?:по\s+(?:мнению|данным|оценке)|согласно|в\s+исследовании)\b", prefix, re.I)
        return bool(POLITICAL_CONTEXT.search(sentence)) and not attributed
    if rule.context_requirement == "political_person_label":
        return _political_person_label(rule, text, start, end, sentence_span, event_context)
    if rule.context_requirement == "territory_terminology":
        return _territory_term_context(rule, text, start, end, sentence_span)
    if rule.context_requirement == "psychological_label":
        return _psychological_label_context(text, start, end, sentence_span, event_context)
    if rule.context_requirement == "human_pest_metaphor":
        return _human_attack_context(text, start, end, sentence_span, event_context, require_actor=True)
    if rule.context_requirement == "human_attack":
        return _human_attack_context(text, start, end, sentence_span, event_context)
    if rule.context_requirement == "bogus_nickname":
        # An adjective modifying a prop, document or institution is not a
        # substituted personal name, even in a political news report.
        tail = text[end:end + 65]
        if re.match(r"\s+(?:[а-яё-]+\s+){0,2}(?:реквизит[а-яё]*|декораци[а-яё]*|"
                    r"макет[а-яё]*|меч[а-яё]*|оружи[а-яё]*|пистолет[а-яё]*|нож[а-яё]*|"
                    r"трон[а-яё]*|корон[а-яё]*|банкнот[а-яё]*|деньг[а-яё]*|денег|"
                    r"дворец[а-яё]*|фасад[а-яё]*|выбор[а-яё]*|демократи[а-яё]*|"
                    r"паспорт[а-яё]*|пропуск[а-яё]*|документ[а-яё]*|удостоверени[а-яё]*)\b", tail, re.I):
            return False
        return _human_attack_context(text, start, end, sentence_span, event_context)
    if rule.context_requirement == "attributed_political_evaluation":
        # Require an explicit attribution in this bounded paragraph. A nearby
        # politician elsewhere in the article does not supply a source.
        left = max(text.rfind("\n", 0, start) + 1, start - 400)
        paragraph = text[left:sentence_span["start"] + len(sentence)]
        report = POLITICAL_SPEAKER_REPORT.search(paragraph)
        speaker_colon = re.search(r"\b(?:Трамп|Путин|Зеленский|Макрон|Байден|Мерц|Стармер)\s*:\s*[«\"“]", paragraph)
        return bool((report or speaker_colon) and POLITICAL_PRESCRIPTION_TARGET.search(paragraph)
                    and not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
                    and not re.search(r"\b(?:компани[а-яё]*|банк[а-яё]*|клуб[а-яё]*|футбол[а-яё]*|спортивн[а-яё]*)\b", paragraph, re.I))
    if rule.context_requirement == "contemporary_regime_label":
        return (not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
                and (not HISTORICAL_LITERAL.search(sentence) or bool(CURRENT_TARGET.search(sentence))))
    if rule.context_requirement == "unnamed_official_report":
        tail = text[end:end + 120]
        name = r"[А-ЯЁA-Z][а-яёa-z’'-]+\s+[А-ЯЁA-Z][а-яёa-z’'-]+"
        if re.match(r"\s*[,—:(-]?\s*" + name, tail):
            return False
        prefix = text[max(sentence_span["start"], start - 100):start]
        if re.search(name + r"\s*,\s*$", prefix):
            return False
        return bool(re.search(r"\b(?:по\s+(?:словам|данным)|со\s+ссылкой\s+на|"
                              r"(?:сославшись|ссылаясь)\s+на|заявил[а-яё]*|сообщил[а-яё]*|"
                              r"сказал[а-яё]*|рассказал[а-яё]*|отметил[а-яё]*)\s*$", prefix, re.I)
                    or re.match(r"\s*:\s*[«\"“]", tail)
                    or re.match(r"\s*[,—:-]?\s*(?:(?:недавно|сегодня|вчера|также|анонимно)\s+){0,2}"
                                r"(?:заявил[а-яё]*|сообщил[а-яё]*|рассказал[а-яё]*|сказал[а-яё]*|"
                                r"отметил[а-яё]*|пояснил[а-яё]*|подтвердил[а-яё]*|добавил[а-яё]*|"
                                r"считает|полагает|говорит|сообщает|утверждает|предупредил[а-яё]*)\b", tail, re.I))
    if rule.context_requirement == "russian_ukrainian_terminology":
        # A publisher's identity never supplies the conflict context. Limit it
        # to nearby text; explicit other wars and technical acronyms take priority.
        nearby = text[max(0, start - 350):min(len(text), end + 350)] + "\n" + event_context
        if OTHER_WAR_CONTEXT.search(sentence) or LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
            return False
        if rule.id == "terminology.svo" and OTHER_SVO.search(nearby):
            return False
        return bool(WAR_PARTICIPANT.search(nearby) and WAR_ACTION.search(sentence + "\n" + event_context))
    if rule.context_requirement.startswith("quantitative_"):
        tail = text[end:end + 100]
        if DIRECT_QUANTITY.match(tail) or CLAUSE_QUANTITY.search(tail):
            return False
        if rule.context_requirement == "quantitative_prevalence":
            return bool(GROUP_ASSERTION.search(sentence))
        if rule.context_requirement == "quantitative_frequency":
            return bool(PUBLIC_EVENT.search(sentence) and EVENT_ASSERTION.search(sentence))
        # Keep the count subject in the same clause. An unrelated earlier
        # number/actor must not license a qualitative comparison of size/height.
        prefix = re.split(r"[,;:]", text[sentence_span["start"]:start])[-1]
        suffix = re.split(r"[,;:.!?\n]", tail)[0]
        return bool(COUNT_CONTEXT.search(prefix + " " + suffix)) and not DIRECT_DIFFERENCE.match(tail)
    if rule.context_requirement == "nonfiction":
        return not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
    if rule.context_requirement == "headline_or_lead":
        return (field == "title" or start < 220) and not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
    if rule.context_requirement == "collective_blame":
        nearby = text[max(0, start - 250):min(len(text), end + 250)] + " " + event_context
        return bool(re.search(r"\b(?:сомали[а-яё]*|европейц[а-яё]*|россиян[а-яё]*|украинц[а-яё]*|"
                              r"американц[а-яё]*|мигрант[а-яё]*|беженц[а-яё]*|чиновник[а-яё]*|"
                              r"политик[а-яё]*)\b", nearby, re.I)) and not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
    if rule.context_requirement == "quote_omission":
        index = bisect_right(quotes, start, key=lambda interval: interval[0]) - 1
        return index >= 0 and end <= quotes[index][1]
    if rule.context_requirement in {"political_speech_metaphor", "political_nickname", "political_mocking_emoji", "group_mental_state"}:
        nearby = text[max(0, start - 900):min(len(text), end + 200)]
        if not POLITICAL_CONTEXT.search(nearby) or LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
            return False
        if rule.context_requirement == "political_speech_metaphor":
            return not LITERAL_ANIMAL_CONTEXT.search(sentence)
        if rule.context_requirement == "political_mocking_emoji":
            return not re.search(r"\b(?:цирк[а-яё]*|клоун[а-яё]*|маскарад[а-яё]*)\b", sentence, re.I)
        if rule.context_requirement == "political_nickname":
            return not re.match(
                r"\s+(?:срок[а-яё]*|продукт[а-яё]*|лекарств[а-яё]*|паспорт[а-яё]*|пропуск[а-яё]*|"
                r"мандат[а-яё]*|договор[а-яё]*|кредит[а-яё]*|плат[её]ж[а-яё]*|сч[её]т[а-яё]*|"
                r"долг[а-яё]*|задолженност[а-яё]*|билет[а-яё]*|сертификат[а-яё]*|вакцин[а-яё]*|"
                r"товар[а-яё]*|документ[а-яё]*|удостоверени[а-яё]*|разрешени[а-яё]*)\b",
                text[end:end + 80], re.I,
            )
        # A quantified subset is different from assigning one attitude to a
        # whole population. This is local scope, not a survey fact check.
        prefix = text[max(sentence_span["start"], start - 65):start]
        return not re.search(
            r"\b(?:часть|большинство|меньшинство|некоторые|многие|немногие|несколько)\s*$|"
            r"(?:\d+(?:[.,]\d+)?\s*%|\d+\s+процент[а-яё]*)\s*$", prefix, re.I,
        )
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
    ] + [{"id": key, "label": LABELS[key], "coverage": "context_notices"}
         for key in sorted(INFORMATIONAL)]


def validate_document(document):
    if not isinstance(document, dict):
        raise ValueError("Ожидается JSON-объект с полями title и text.")
    unknown = set(document) - {"title", "text", "source", "url", "published_at", "media"}
    if unknown:
        raise ValueError("Неизвестные поля документа: " + ", ".join(sorted(unknown)))
    for field in ("title", "text", "source", "url", "published_at"):
        if field in document and not isinstance(document[field], str):
            raise ValueError(f"Поле {field} должно быть строкой.")
    if "media" in document:
        media = document["media"]
        if (not isinstance(media, dict) or set(media) != {"image_count"}
                or type(media["image_count"]) is not int or not 0 <= media["image_count"] <= 100):
            raise ValueError("Поле media должно содержать только целое image_count от 0 до 100; содержимое фото не анализируется.")
    title, text = document.get("title", ""), document.get("text", "")
    if not text.strip():
        raise ValueError("Поле text должно содержать текст публикации.")
    if sum(len(value) for value in document.values() if isinstance(value, str)) > MAX_CHARS:
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
    negated = bool(re.search(r"\bне\s+(?!(?:только|меньше|больше|менее|более|хуже|лучше)\b)(?:\w+\s+){0,2}$", prefix, re.I))
    # Not forgiving/supporting a target does not negate the target's epithet.
    # Explicit denial below still takes priority; this is a bounded local cue.
    if re.search(r"\bне\s+(?:должен|должна|должны|следует|нужно|надо)\s+"
                 r"(?:прощать|жалеть|поддерживать|защищать)\s*$", prefix, re.I):
        negated = False
    discussed = bool(re.search(
        r'\b(?:слово|слова|выражение|фраза|формулировка|формулировку|термин|ярлык|тезис|лозунг|слоган|клише|цитата|пример|эмодзи|символ|значок)\s*[:«"“„—-]?\s*$', prefix, re.I,
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
        r"\s*,\s*(?:что|будто)\s+(?:[а-яё]+\s+){0,3}(?:[—:-]\s*)?[«\"“„]?\s*$",
        text[sentence["start"]:start][-180:], re.I,
    ))
    statement_prefix = text[sentence["start"]:start][-220:]
    reported = bool(re.search(
        r"\b(?:заявил[а-яё]*|сказал[а-яё]*|назвал[а-яё]*|утвержда[а-яё]*|отметил[а-яё]*|"
        r"написал[а-яё]*|сообщил[а-яё]*|пояснил[а-яё]*|подчеркнул[а-яё]*|"
        r"считает|считают|пишет|пишут|сообщает|сообщают|отмечает|отмечают|по\s+(?:(?:его|её|ее|их|собственным)\s+)?(?:словам|мнению|убеждению))\b[^.!?\n]{0,110}$", statement_prefix, re.I,
    ) or re.search(
        r"^\s*(?:[»”\"]\s*)?[.!?]?\s*(?:[,—-]\s*|,\s*[—-]\s*)(?:так\s+)?"
        r"(?:(?!(?:но|однако|а|и)\b)[^.!?\n]{0,45}\s+)?"
        r"(?:назвал[а-яё]*|заявил[а-яё]*|сказал[а-яё]*|отметил[а-яё]*|подытожил[а-яё]*)\b",
        text[end:min(len(text), end + 140)], re.I,
    ))
    suffix = sentence["text"][end - sentence["start"]:]
    contrast = re.search(r"[,;]\s*(?:но|однако|а|зато)\b", suffix, re.I)
    if not contrast:
        reported = reported or bool(re.search(
            r",\s*(?:как\s+)?(?:пишет|пишут|сообщает|сообщают|отмечает|отмечают|"
            r"признал[а-яё]*|заявил[а-яё]*|сказал[а-яё]*)\s+"
            r"(?!(?:о|об|что|как)\b)[^.!?\n]{1,60}[.!?]?\s*$", suffix, re.I,
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


def _parallel_units(title, text):
    """Bounded sentences/lines with original offsets, never normalized prose."""
    units = []
    base = 0
    for field, value in (("title", title), ("text", text)):
        for match in re.finditer(r"[^.!?\r\n]+[.!?]*", value):
            part = match.group()
            start = match.start() + len(part) - len(part.lstrip())
            end = match.end() - len(part) + len(part.rstrip())
            if start == end:
                continue
            sentence = value[start:end]
            named_current = CURRENT_TARGET.search(sentence)
            current = named_current
            if current is None and POLITICAL_CONTEXT.search(sentence):
                current = MODERN_CUE.search(sentence)
            historical = HISTORICAL_ANCHOR.search(sentence)
            allowed = len(sentence) <= 600 and not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
            themes = {key for key, (_, pattern) in PARALLEL_THEMES.items()
                      if allowed and pattern.search(sentence)}
            units.append({"field": field, "start": start, "end": end,
                          "document_start": base + start, "document_end": base + end,
                          "text": sentence, "themes": themes,
                          "current": bool(allowed and current and not historical
                                          and not HISTORICAL_LITERAL.search(sentence)),
                          "historical": bool(allowed and historical and not named_current),
                          "anchor_start": start + (historical or current).start() if historical or current else start,
                          "anchor_end": start + (historical or current).end() if historical or current else end})
        base += len(value) + 1
    return units


def _historical_juxtapositions(title, text, quotes):
    """Suggest a relation between nearby passages, not a verdict about history.

    Search at most five units either side and 1800 characters. Two matching
    themes are needed in EACH pair. Publisher identity supplies no context.
    """
    units = _parallel_units(title, text)
    values = {"title": title, "text": text}
    rule = HISTORICAL_JUXTAPOSITION
    for index, modern in enumerate(units):
        if not modern["current"] or len(modern["themes"]) < 2:
            continue
        related, shared = [], set()
        lower, upper = max(0, index - PARALLEL_NEIGHBOURS), min(len(units), index + PARALLEL_NEIGHBOURS + 1)
        for other in range(lower, upper):
            historical = units[other]
            overlap = modern["themes"] & historical["themes"]
            if not historical["historical"] or len(overlap) < 2:
                continue
            gap = max(modern["document_start"], historical["document_start"]) - min(
                modern["document_end"], historical["document_end"])
            if gap > PARALLEL_DISTANCE:
                continue
            # Another current story is a boundary; do not stitch unrelated leads.
            if any(unit["current"] for unit in units[min(index, other) + 1:max(index, other)]):
                continue
            related.append(other)
            shared.update(overlap)
        if not related:
            continue
        members = [modern] + [units[i] for i in related]
        first, last = min(index, *related), max(index, *related)
        context = units[max(0, first - 1):min(len(units), last + 3)]
        rejected = any(REJECTED_PARALLEL.search(unit["text"]) for unit in context)
        # Quoted source statements do not mean their EDITORIAL arrangement was
        # itself quoted. Only one common outer quote can attribute the relation.
        quoted_relation = False
        if len({member["field"] for member in members}) == 1:
            field = modern["field"]
            left = min(member["anchor_start"] for member in members)
            right = max(member["anchor_end"] for member in members)
            quoted_relation = any(a <= left and right <= b for a, b in quotes[field])
        evidence = []
        for member in members:
            item = _evidence(member["field"], values[member["field"]],
                             member["start"], member["end"], quotes[member["field"]])
            item["context"]["historical_analogy"] = True
            evidence.append(item)
        yield {"rule_id": rule.id, "category": rule.category, "label": "Историческая аналогия",
               "status": "context_only" if rejected else "quoted_candidate" if quoted_relation else "needs_review",
               "explanation": rule.explanation + " Повторяющиеся темы: " +
                              "; ".join(PARALLEL_THEMES[key][0] for key in sorted(shared)) + ".",
               "review_question": rule.review_question, "evidence": evidence}


def _rhetorical_notices(title, text, quotes, findings, image_count=0):
    """Observe composition, never infer what photographs show or who is implied.

    Rank/polarity pairs are at most three units and 600 characters apart. The
    metadata records preview attachments only; no images are fetched by analyze.
    """
    units = _parallel_units(title, text)
    values = {"title": title, "text": text}

    def notice(rule_id, label, members, **observations):
        rule = STRUCTURAL_NOTICES[rule_id]
        evidence = []
        for member in members:
            item = _evidence(member["field"], values[member["field"]], member["start"], member["end"], quotes[member["field"]])
            item["context"].update(informational_notice=True, **observations)
            evidence.append(item)
        return {"rule_id": rule.id, "category": rule.category, "label": label,
                "status": "context_only", "explanation": rule.explanation,
                "review_question": rule.review_question, "evidence": evidence}

    linked_history = [e for f in findings if f["rule_id"] in {
        "simplification.historical_juxtaposition", "simplification.historical_parallel", "enemy.nazi_analogy"}
        for e in f["evidence"]]
    for unit in units:
        # A historical name alone, publication date or publisher never supplies
        # an implied modern target. Require editorial selection AND a quotation.
        if (unit["historical"] and not any(e["field"] == unit["field"] and e["start"] < unit["end"]
                                            and unit["start"] < e["end"] for e in linked_history)
                and HISTORICAL_SELECTION.search(unit["text"])
                and not HISTORICAL_STUDY.search(unit["text"])
                and any(unit["start"] <= a <= unit["end"] + 180 and b - a >= 20
                        for a, b in quotes[unit["field"]])):
            yield notice("context.historical_reference", "Историческая отсылка", [unit],
                         historical_reference=True, modern_target_identified=False)

    used_units = set()
    for index, first in enumerate(units):
        if len(first["text"]) > 600:
            continue
        for other in range(index, min(len(units), index + 4)):
            second = units[other]
            if len(second["text"]) > 600 or second["document_start"] - first["document_end"] > 600:
                continue
            members = [first] if index == other else [first, second]
            joined = " ".join(member["text"] for member in members)
            photo_pair = bool(FIRST_PHOTO.search(joined) and SECOND_PHOTO.search(joined))
            opposite = bool((POSITIVE_POLE.search(first["text"]) and NEGATIVE_POLE.search(second["text"]))
                            or (NEGATIVE_POLE.search(first["text"]) and POSITIVE_POLE.search(second["text"])))
            comparable = (opposite and COMPARISON_LINK.search(joined)
                          and all(RANKING_CUE.search(member["text"]) for member in members)
                          and (index != other or len(RANKING_CUE.findall(joined)) >= 2))
            if not (photo_pair or comparable):
                continue
            pair = tuple((member["field"], member["start"], member["end"]) for member in members)
            # Avoid repeating a first pair as more surrounding units are visited.
            if used_units.intersection(pair):
                continue
            used_units.update(pair)
            if comparable:
                yield notice("context.evaluative_comparison", "Сравнение и противопоставление", members,
                             evaluative_comparison=True)
            if photo_pair or image_count >= 2:
                yield notice("context.visual_comparison", "Сравнение иллюстраций", members,
                             visual_comparison=True, images_analyzed=False,
                             **({"image_count": image_count} if image_count else {}))


def analyze(document):
    """Return exact spans relative to unchanged input, in Unicode code points."""
    title, text = validate_document(document)
    quotes = {"title": _quote_ranges(title), "text": _quote_ranges(text)}
    findings = []
    occupied = {}
    truncated = False
    # Informational terms must not exhaust the budget before rhetoric in either field.
    for informational in (False, True):
        for field, value in (("title", title), ("text", text)):
            for rule, pattern in COMPILED_RULES:
                if (rule.category in INFORMATIONAL) != informational:
                    continue
                if field not in rule.fields:
                    continue
                for match in pattern.finditer(value):
                    if not _rule_applies(rule, field, value, *match.span(), quotes[field],
                                         event_context=text[:350] if field == "title" else title):
                        continue
                    spans = occupied.setdefault((field, rule.category), [])
                    if any(match.start() < end and start < match.end() for start, end in spans):
                        continue
                    if len(findings) >= MAX_FINDINGS:
                        truncated = True
                        break
                    evidence = _evidence(field, value, *match.span(), quotes[field])
                    if (rule.context_requirement == "political_person_label" or rule.id == "dysphemism.autocratic_label") and re.match(
                        r"\s*[»\"”]?\s+(?:назвали|называют|считают)\s+"
                        r"(?:(?-i:[А-ЯЁ][а-яё-]{1,30})\s+){0,2}" + POLITICAL_PERSON + r"\b",
                        value[match.end():match.end() + 140], re.I,
                    ):
                        evidence["context"]["reported_speech"] = True
                    if rule.id in {"authority.prominent_prescriptive_quote", "authority.attributed_political_evaluation"}:
                        # This rule requires attributed speech even without literal
                        # quotation marks. Denial/discussion still take priority.
                        evidence["context"]["reported_speech"] = True
                    if rule.id == "context.quotation_omission":
                        # Editing is observable; distortion is not established.
                        evidence["context"]["quotation_edited"] = True
                    if rule.category in INFORMATIONAL:
                        evidence["context"]["informational_notice"] = True
                    spans.append(match.span())
                    findings.append({
                        "rule_id": rule.id, "category": rule.category, "label": LABELS[rule.category],
                        "status": "context_only" if rule.id == "context.quotation_omission" or rule.category in INFORMATIONAL else _status(evidence),
                        "explanation": rule.explanation,
                        "review_question": rule.review_question, "evidence": [evidence],
                    })
        if informational:
            for finding in _rhetorical_notices(title, text, quotes, findings,
                                               document.get("media", {}).get("image_count", 0)):
                if len(findings) >= MAX_FINDINGS:
                    truncated = True
                    break
                findings.append(finding)
            continue
        for finding in _historical_juxtapositions(title, text, quotes):
            if len(findings) >= MAX_FINDINGS:
                truncated = True
                break
            findings.append(finding)
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
        # Operational rating weight, separate from attribution and semantics.
        # A notice, quotation or denial remains labelled as such.
        finding["rating_weight"] = 1
    active = Counter(f["category"] for f in findings if f["status"] == "needs_review")
    content = {"title": title, "text": text, **({"media": dict(document["media"])} if "media" in document else {})}
    digest = hashlib.sha256(json.dumps(content, ensure_ascii=False,
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
                     **({"media": dict(document["media"])} if "media" in document else {}),
                     **{key: document[key] for key in ("source", "url", "published_at") if key in document},
                     "sha256": digest},
        "offset_unit": "unicode_code_points", "findings": findings,
        "summary": {"marker_count": len(findings),
                    "marker_fragments": len({(e["field"], e["start"], e["end"])
                                             for f in findings for e in f["evidence"]}),
                    "review_candidates": sum(active.values()), "by_category": dict(active),
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

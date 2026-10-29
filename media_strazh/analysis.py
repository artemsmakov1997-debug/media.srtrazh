"""Deterministic candidates for human review; no inference of intent or truth."""

from bisect import bisect_right
from collections import Counter
from decimal import Decimal
import calendar
import hashlib
import json
import re

from .rules import HISTORICAL_JUXTAPOSITION, RULES

VERSION = "rules-0.16.0"
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
LABELS["rhetorical_context"] = "Контекст подачи и сопоставления"
INFORMATIONAL = {"event_terminology", "actor_terminology", "territory_terminology", "rhetorical_context"}
RULE_LABELS = {
    "terminology.denazification": "Обозначение «денацификация»",
    "terminology.demilitarization": "Обозначение «демилитаризация»",
    "terminology.anti_russian": "Характеристика «антироссийский»",
    "terminology.liberal_actor": "Обозначение взглядов «либерал»",
    "terminology.political_persecution": "Квалификация политического преследования",
    "terminology.repression": "Квалификация «репрессии»",
    "terminology.oppression": "Обозначение «угнетение»",
    "dysphemism.ideological_slur": "Уничижительный идеологический ярлык",
    "dysphemism.bought_voice": "Обвинение в продажности или оплате",
    "context.double_standards": "Обвинение в двойных стандартах",
    "enemy.betrayal_label": "Ярлык «предатель»",
    "terminology.collective_west": "Обобщение «Коллективный Запад»",
    "terminology.western_partners": "Обозначение «Западные партнёры»",
    "terminology.geopolitical_west": "Обобщённое обозначение Запада",
    "dysphemism.putinoid_group": "Групповой ярлык «путиноид»",
    "dysphemism.vatnik_group": "Групповой ярлык «ватник»",
    "terminology.occupier_actor": "Обозначение участника «оккупант»",
    "terminology.liberator_actor": "Обозначение участника «освободитель»",
    "terminology.propagandist_actor": "Обозначение роли «пропагандист»",
    "simplification.question_deflection": "Отвод от вопроса",
    "simplification.consequence_chain": "Цепочка последствий",
    "simplification.circular_justification": "Круговое обоснование",
    "simplification.absence_as_concealment": "Отсутствие доказательств как подтверждение",
    "context.unspecified_measures": "Неконкретные меры",
    "context.unattributed_decision": "Неуказанный субъект решения",
}
SUPPORTED = {key for key, _, supported in TAXONOMY if supported}


COMPILED_RULES = [(rule, re.compile(rule.pattern, re.IGNORECASE)) for rule in RULES
                  if rule.context_requirement not in {"historical_juxtaposition", "structural_notice", "literature_structure"}]
STRUCTURAL_NOTICES = {rule.id: rule for rule in RULES if rule.context_requirement == "structural_notice"}
LITERATURE_NOTICES = {rule.id: rule for rule in RULES if rule.context_requirement == "literature_structure"}
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


def _framing_context(rule, sentence, before, after):
    """Disambiguate the new vocabulary locally; retain factual/history notices."""
    kind = rule.context_requirement
    if kind == "framing_term":
        return True
    if kind == "demilitarization_term":
        cyber_tail = re.match(r"\s+(?:зон[а-яё]*\s*(?:[([]\s*)?)?"
                              r"(?:DMZ|сервер[а-яё]*|маршрутизатор[а-яё]*|"
                              r"(?:компьютерн|локальн|корпоративн|офисн|сетев)[а-яё]*\s+"
                              r"(?:сет[ьи][а-яё]*|сегмент[а-яё]*|периметр[а-яё]*|зон[а-яё]*))\b", after, re.I)
        cyber_subject = re.search(r"\b(?:сервер[а-яё]*|маршрутизатор[а-яё]*|ф(?:ай|ае|айе)рвол[а-яё]*)\s+"
                                 r"(?:(?:находит[а-яё]*|размещ[а-яё]*|помещ[а-яё]*|расположен[а-яё]*|стоит)\s+)?"
                                 r"(?:в|из)\s*$", before[-100:], re.I)
        return not (cyber_tail or cyber_subject)
    if kind == "comparison_standards_term":
        return not re.match(r"\s+(?:напряжения|кодировки|резьбы|разъ[её]м(?:а|ов)|передачи\s+данных)\b", after, re.I)
    if kind == "framing_label":
        if re.search(r"\b(?:сыграл[а-яё]*|играл[а-яё]*|в\s+роли)\s+(?:роль\s+)?$", before, re.I):
            return False
        real_speaker = re.search(r"\b(?:акт[её]р[а-яё]*|режисс[её]р[а-яё]*|писател[а-яё]*)\b", before, re.I)
        attributed = re.search(r"\b(?:назвал[а-яё]*|обозвал[а-яё]*|заявил[а-яё]*)\b"
                               r"(?:(?!\b(?:геро[а-яё]*|персонаж[а-яё]*)\b)[^.!?]){0,90}$", before, re.I)
        if real_speaker and attributed:
            return True
        work = re.search(r"\b(?:роман(?:а|е|у|ом)?|фильм(?:а|е|у|ом)?|сериал(?:а|е|у|ом)?|"
                         r"спектакл(?:я|е|ю|ем|ь)|игр(?:а|е|ы|у|ой))\b", sentence, re.I)
        role = re.search(r"\b(?:геро(?:й|я|и|ев|ем)|персонаж[а-яё]*|сюжет[а-яё]*|"
                         r"игрок[а-яё]*|настольн[а-яё]*|компьютерн[а-яё]*)\b", sentence, re.I)
        return not (work and role or re.search(r"\bпо\s+сюжету\b", sentence, re.I))
    if kind == "rights_term":
        if rule.id == "terminology.repression":
            if re.match(r"\s+(?:(?:экспрессии|активности)\s+)?(?:ген(?:а|ов)|белк(?:а|ов)|транскрипции|трансляции|оперона|ДНК|РНК)\b", after, re.I):
                return False
            return not re.search(r"\b(?:генн|генетическ|транскрипционн|эпигенетическ)[а-яё]*\s*$", before, re.I)
        if rule.id == "terminology.oppression":
            if re.match(r"\s+(?:(?:центральной|периферической)\s+)?(?:дыхания|сознания|ЦНС|нервной\s+системы|"
                        r"кроветворения|костного\s+мозга|дыхательного\s+центра|роста|синтеза|метаболизма|"
                        r"фермент[а-яё]*|фотосинтеза|иммунитет[а-яё]*|иммунн[а-яё]*\s+систем[а-яё]*|"
                        r"растений|рассады|всходов|бактерий|микроорганизмов)\b", after, re.I):
                return False
            social = re.search(r"\b(?:политическ[а-яё]*|народ[а-яё]*|граждан[а-яё]*|людей|"
                               r"женщин[а-яё]*|меньшинств[а-яё]*|верующ[а-яё]*|инакомысли[а-яё]*|"
                               r"несогласн[а-яё]*|работник[а-яё]*|этническ[а-яё]*|социальн[а-яё]*)\b", sentence, re.I)
            return bool(social) or not LITERAL_CLINICAL_CONTEXT.search(sentence)
        return True
    raise ValueError("Неизвестный контекст политической формулировки.")


def _vocabulary_context(rule, text, start, end, sentence_span, event_context):
    """Local word sense guards; never infer irony, truth or political allegiance."""
    sentence = sentence_span["text"]
    before = text[sentence_span["start"]:start]
    after = text[end:sentence_span["end"]]
    # Proper titles and product names are not political labels. A real actor
    # commenting on politics is not excluded merely for being an actor.
    if re.search(r"\b(?:фильм[а-яё]*|роман[а-яё]*|сериал[а-яё]*|спектакл[а-яё]*|книг[а-яё]*|"
                 r"игр[а-яё]*|бренд[а-яё]*|магазин[а-яё]*|компани[а-яё]*|газет[а-яё]*|"
                 r"журнал[а-яё]*|издани[а-яё]*|утилит[а-яё]*|программ[а-яё]*)\s*[«\"“„]\s*$", before, re.I):
        return False
    kind = rule.context_requirement
    if kind in {"framing_term", "demilitarization_term", "rights_term", "framing_label", "comparison_standards_term"}:
        return _framing_context(rule, sentence, before, after)
    if kind in {"collective_actor_term", "supporter_label", "regime_label"}:
        return True
    if kind == "vatnik_group":
        clothing = re.search(r"\b(?:одежд[а-яё]*|телогрейк[а-яё]*|рукав[а-яё]*|подкладк[а-яё]*|"
                             r"куртк[а-яё]*|ст[её]ган[а-яё]*|утепл[её]н[а-яё]*)\b", before[-70:] + after[:50], re.I)
        clothing = clothing or re.search(
            r"\b(?:шить|шьют|сшил[а-яё]*|сшит[а-яё]*|"
            r"надел[а-яё]*|надет[а-яё]*|надев[а-яё]*|одет[а-яё]*|снял[а-яё]*|носил[а-яё]*|носить|носят|"
            r"купил[а-яё]*|купить|покупа[а-яё]*|прода[а-яё]*|стира[а-яё]*|постира[а-яё]*|"
            r"суши[а-яё]*|сохнут|выда[а-яё]*)\s+(?:[а-яё-]+\s+){0,3}$", before[-100:], re.I)
        garment_modifiers = r"(?:(?:стар|нов|рван|ч[её]рн|син|сер|зел[её]н|грязн|т[её]пл|военн)[а-яё]*\s+){0,2}"
        clothing = clothing or (
            re.fullmatch(r"ватник(?:е|ах)", text[start:end], re.I)
            and re.search(r"\bв\s+" + garment_modifiers + r"$", before[-70:], re.I)
        )
        clothing = clothing or re.search(
            r"\bна\s+(?:н[её]м|ней|них|мне|тебе|вас|нас|президенте|политике|солдате|рабочем)"
            r"\s+(?:был(?:а|о|и)?\s+)?" + garment_modifiers + r"$", before[-100:], re.I)
        clothing = clothing or re.match(
            r"\s+(?:(?:был(?:а|о|и)?|сейчас|пока|ещ[её])\s+){0,2}"
            r"(?:леж[а-яё]*|вис[а-яё]*)\s+(?:на|в|под)\s+"
            r"(?:стул[а-яё]*|полу|полк[а-яё]*|вешалк[а-яё]*|шкаф[а-яё]*|плечик[а-яё]*)\b", after, re.I)
        if clothing:
            return False
        address = re.search(r"\b(?:ты|вы|он|она|они)\s*(?:[—:-]\s*|это\s+)?(?:не\s+)?$", before, re.I)
        naming = re.search(r"\b(?:назвал[а-яё]*|называ[а-яё]*|обозвал[а-яё]*|обзыва[а-яё]*|окрестил[а-яё]*)\b",
                           before[-80:], re.I)
        behaviour = re.search(r"\b(?:голосу[а-яё]*|поддержива[а-яё]*|одобря[а-яё]*|"
                              r"счита[а-яё]*|дума[а-яё]*|верят|верит|крича[а-яё]*|"
                              r"говор[а-яё]*|пишут|пишет|спор[а-яё]*|руга[а-яё]*|"
                              r"выбира[а-яё]*|соглаша[а-яё]*|требу[а-яё]*|призыва[а-яё]*)\b", sentence, re.I)
        return bool(address or naming or behaviour or POLITICAL_CONTEXT.search(sentence + " " + event_context))
    if kind == "conflict_actor_term":
        if re.match(r"\s+(?:(?:оперативной|дисковой|свободной)\s+)?"
                    r"(?:памяти|диска|места|кэша|кеша|пространства)\b", after, re.I):
            return False
        pets = re.search(r"\b(?:кот(?:а|у|ом|е|ы|ов|ам|ами|ах)?|кошк[а-яё]*|кот[её]нок|"
                         r"котят[а-яё]*|собак[а-яё]*|щен[а-яё]*)\b", sentence, re.I)
        home = re.search(r"\b(?:диван[а-яё]*|кухн[а-яё]*|кресл[а-яё]*|кроват[а-яё]*|"
                         r"подоконник[а-яё]*)\b", sentence, re.I)
        return not (pets and home)
    if kind == "propagandist_term":
        return not re.match(r"\s+(?:здорового\s+образа\s+жизни|науки|спорта|трезвости|"
                            r"чтения|грамотности|образования|туризма|правил\s+дорожного\s+движения)\b", after, re.I)
    if kind == "geopolitical_west":
        if TERRITORY_AFTER.search(after) or re.match(r"\s+(?:страны|области|региона|района|острова|города|материка|континента|"
                    r"полуострова|Европы|России|Украины)\b", after, re.I):
            return False
        movement = re.search(r"\b(?:поезд[а-яё]*|маршрут[а-яё]*|путешеств[а-яё]*|дорог[а-яё]*|"
                             r"двиг[а-яё]*|двин[а-яё]*|пош[её]л[а-яё]*|пошли|ехать|ехал[а-яё]*|поех[а-яё]*|"
                             r"посмотрел[а-яё]*|повернул[а-яё]*|развернул[а-яё]*|компас[а-яё]*|"
                             r"ветер|направлени[а-яё]*|сторон[а-яё]*\s+света)\b", before, re.I)
        directional = re.search(r"\b(?:на|к|с|со|из)\s+(?:(?:крайн|дал[её]к|дальн)[а-яё]*\s+)?"
                                r"(?:северо-|юго-)?$", before, re.I)
        if movement and directional:
            return False
        action = re.match(r"\s*(?:[—:-]\s*)?(?:(?:вновь|снова|уже|теперь|первым|якобы|"
                          r"всегда|намерен|продолжает)\s+){0,3}"
                          r"(?:(?:это|наш|главный|ключевой|общий)\s+){0,2}"
                          r"(?:ввод[а-яё]*|заяв[а-яё]*|потреб[а-яё]*|требу[а-яё]*|одобр[а-яё]*|"
                          r"поддерж[а-яё]*|решил[а-яё]*|навя[а-яё]*|угрожа[а-яё]*|отказ[а-яё]*|"
                          r"выступ[а-яё]*|обеща[а-яё]*|добива[а-яё]*|финансир[а-яё]*|соглас[а-яё]*|"
                          r"вмешива[а-яё]*|осужда[а-яё]*|счита[а-яё]*|хочет|хотел[а-яё]*|"
                          r"пыта[а-яё]*|стреми[а-яё]*|собира[а-яё]*|готовит[а-яё]*|планиру[а-яё]*|"
                          r"вед[её]т|рассчитыва[а-яё]*|призыва[а-яё]*|призна[а-яё]*|провоцир[а-яё]*|"
                          r"помога[а-яё]*|лж[её]т|лгут|враг|союзник|противник)\b", after, re.I)
        physical = re.search(r"\b(?:солнц[а-яё]*|закат[а-яё]*|ветер|дожд[а-яё]*|снег[а-яё]*|"
                             r"циклон[а-яё]*|ураган[а-яё]*|пожар[а-яё]*|землетрясени[а-яё]*)\b", sentence, re.I)
        if physical and not action:
            return False
        political = POLITICAL_CONTEXT.search(sentence) or re.search(
            r"\b(?:санкци[а-яё]*|дипломат[а-яё]*|НАТО|альянс[а-яё]*|переговор[а-яё]*|"
            r"элит[а-яё]*|вооружени[а-яё]*|военн[а-яё]*|эконом(?:ик|ическ)[а-яё]*|инвестиц[а-яё]*|"
            r"финансир[а-яё]*|сотрудничеств[а-яё]*)\b", sentence, re.I)
        object_role = re.search(r"\b(?:критику[а-яё]*|осужда[а-яё]*|обвиня[а-яё]*|"
                                r"противосто[а-яё]*)\s+(?:(?:коллективный|весь)\s+)?$", before, re.I)
        return bool(action or political or object_role)
    raise ValueError("Неизвестный контекст словаря.")


def _rule_applies(rule, field, text, start, end, quotes=(), event_context=""):
    if field not in rule.fields:
        return False
    if not rule.context_requirement:
        return True
    sentence_span = _sentence(text, start, end)
    sentence = sentence_span["text"]
    fragment = text[start:end]
    if rule.context_requirement in {"collective_actor_term", "geopolitical_west", "vatnik_group",
                                    "conflict_actor_term", "propagandist_term", "supporter_label", "regime_label",
                                    "framing_term", "demilitarization_term", "rights_term", "framing_label", "comparison_standards_term"}:
        return _vocabulary_context(rule, text, start, end, sentence_span, event_context)
    if rule.context_requirement in {"public_discourse", "consequence_chain", "unspecified_measures", "unattributed_decision"}:
        if LITERAL_ENTERTAINMENT_CONTEXT.search(sentence):
            return False
        nearby = text[max(0, start - 220):min(len(text), end + 280)]
        public = bool(POLITICAL_CONTEXT.search(fragment) or re.search(
            r"\b(?:бюджет[а-яё]*|налог[а-яё]*|тариф[а-яё]*|цен[а-яё]*|митинг[а-яё]*|"
            r"реформ[а-яё]*|закон[а-яё]*|пенси[а-яё]*|пособи[а-яё]*|гражданск[а-яё]*)\b", fragment, re.I))
        if not public:
            # Generic measures require a local public subject, not an unrelated
            # political paragraph elsewhere in the document.
            public = rule.context_requirement == "unspecified_measures" and bool(POLITICAL_CONTEXT.search(nearby + " " + event_context))
        if not public:
            return False
        if rule.context_requirement == "consequence_chain":
            last = re.split(r"[—–-]|\b(?:затем|потом|следом|в\s+итоге|в\s+конце\s+концов)\b", fragment, flags=re.I)[-1]
            return not (re.search(r"\b(?:не|без)\s+(?:[а-яё]+\s+){0,2}(?:развал[а-яё]*|разруш[а-яё]*|"
                                  r"катастроф[а-яё]*|диктатур[а-яё]*|гражданск[а-яё]*)\b", last, re.I)
                        or re.match(r"\s+(?:не|никак\s+не)\s+(?:будет|случится|произойдёт|произойдет)\b",
                                    text[end:end + 55], re.I))
        if rule.context_requirement == "unspecified_measures":
            detail = text[max(0, start - 150):min(len(text), end + 280)]
            return not re.search(r"\b(?:в\s+частности|а\s+именно|например|меры\s+включают|"
                                 r"проверят|опубликуют|снизят|запретят|направят|выделят|создадут|"
                                 r"введут|увеличат|закроют|откроют|отремонтируют|проиндексируют)\b|"
                                 r"меры\s*:\s*\S", detail, re.I)
        if rule.context_requirement == "unattributed_decision":
            return not re.search(r"\b(?:правительств[а-яё]*|президент[а-яё]*|министр[а-яё]*|"
                                 r"министерств[а-яё]*|депутат[а-яё]*|губернатор[а-яё]*|мэр[а-яё]*|"
                                 r"администраци[а-яё]*|ведомств[а-яё]*|парламент[а-яё]*|совет[а-яё]*|"
                                 r"дума|думой|суд[а-яё]*|комисси[а-яё]*)\b", nearby + " " + event_context, re.I)
        return True
    if rule.context_requirement == "affirmative_inference":
        conclusion = re.split(r"\b(?:значит|следовательно|поэтому)\b", fragment, flags=re.I)[-1]
        return (not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
                and not re.search(r"\b(?:не|нельзя)\b", conclusion, re.I))
    if rule.context_requirement == "guilt_pressure":
        guilt = re.search(r"\bна\s+(?:твоей|вашей)\s+совести\b", fragment, re.I)
        rejected = guilt and re.search(r"\bне\s+(?:(?:будет|будут|ляжет|лягут|останется|останутся)\s+)?$",
                                      fragment[max(0, guilt.start() - 45):guilt.start()], re.I)
        return not rejected and not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
    if rule.context_requirement == "inaccessible_evidence":
        return (not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
                and not re.search(r"\bне\s+(?:засекречен[а-яё]*|секретн[а-яё]*|недоступн[а-яё]*)\b", fragment, re.I))
    if rule.context_requirement == "public_promise":
        return (not LITERAL_ENTERTAINMENT_CONTEXT.search(sentence)
                and not re.search(r"\bне\s+(?:избав[а-яё]*|обеспеч[а-яё]*|защит[а-яё]*|спас[а-яё]*)\b", fragment, re.I)
                and bool(POLITICAL_CONTEXT.search(sentence) or re.search(
                    r"\b(?:закон[а-яё]*|экономик[а-яё]*|населени[а-яё]*|реформ[а-яё]*)\b", sentence, re.I)))
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
    if quoted:
        # A marker may occur deep inside a multi-sentence teaching quotation.
        # Its introductory «Фраза / пример:» belongs to the whole outer quote.
        quote_start = quotes[quote_index][0]
        discussed = discussed or bool(re.search(
            r"\b(?:слово|слова|выражение|фраза|формулировка|термин|ярлык|тезис|лозунг|слоган|клише|цитата|пример)"
            r"\s*[:—-]?\s*$", text[max(0, quote_start - 100):quote_start], re.I,
        ))
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


NUMERIC_AMOUNT = r"(?:[0-9]{1,3}(?:[ \u00a0\u202f][0-9]{3})+|[0-9]+)(?:[.,][0-9]+)?"
NUMERIC_SCALE = r"(?:тыс\.?|тысяч(?:а|и|у)?|млн\.?|миллион(?:а|ов)?|млрд\.?|миллиард(?:а|ов)?)"
NUMERIC_METRIC = r"[а-яё]+(?:[ -][а-яё]+){0,3}?"
DAILY_NUMBER = re.compile(
    rf"(?<![\w.,])(?P<number>{NUMERIC_AMOUNT})\s*(?P<scale>{NUMERIC_SCALE})?\s+"
    rf"(?P<metric>{NUMERIC_METRIC})\s+(?:в\s+(?:день|сутки)|каждый\s+день|ежедневно)\b", re.I)
ANNUAL_NUMBER = re.compile(
    rf"(?<![\w.,])(?P<number>{NUMERIC_AMOUNT})\s*(?P<scale>{NUMERIC_SCALE})?\s+"
    rf"(?P<metric>{NUMERIC_METRIC})?\s*(?:в|за)\s+(?:весь\s+)?"
    r"(?:(?P<year>(?:19|20)[0-9]{2})\s*)?(?:год(?:а|у)?\b|г\.(?=\s|$))", re.I)
MAJORITY_WORD = r"(?:(?:подавляющее|абсолютное)\s+)?(?:большинство|большая\s+часть|подавляющее\s+число)"
NUMERIC_PERCENT = r"(?:от\s+)?[0-9]{1,3}(?:[.,][0-9]{1,3})?(?:\s*(?:[-–—]|до)\s*[0-9]{1,3}(?:[.,][0-9]{1,3})?)?\s*%"
MAJORITY_FORWARD = re.compile(
    rf"\b(?P<majority>{MAJORITY_WORD})\b(?P<group>[^0-9.!?%\n—–:=()\-]{{0,90}}?)"
    rf"\s*(?:[—–:=\-(]|,?\s*(?:то\s+есть|а\s+именно)\s+)\s*(?P<percent>{NUMERIC_PERCENT})", re.I)
MAJORITY_REVERSE = re.compile(
    rf"(?<![0-9.,])(?P<percent>{NUMERIC_PERCENT})(?P<group>[^0-9.!?%\n—–:=()\-]{{0,90}}?)"
    rf"\s*[—–:=\-]\s*(?:это\s+)?(?P<majority>{MAJORITY_WORD})\b", re.I)
NUMERIC_GROUP = re.compile(
    r"\b(?:участник[а-яё]*|опрошенн[а-яё]*|респондент[а-яё]*|избирател[а-яё]*|"
    r"жител[а-яё]*|граждан[а-яё]*|депутат[а-яё]*|населени[а-яё]*|голос[а-яё]*)\b", re.I)
NUMERIC_SCOPE_GUARD = re.compile(
    r"\b(?:относительн[а-яё]*|определивш[а-яё]*|взросл[а-яё]*|мужчин[а-яё]*|женщин[а-яё]*|"
    r"молод[а-яё]*|пенсионер[а-яё]*|сторонник[а-яё]*|противник[а-яё]*|"
    r"полностью|частично|скорее|лишь|только|среди|коалици[а-яё]*|мандат[а-яё]*|"
    r"оставш[а-яё]*|пришедш[а-яё]*|ответивш[а-яё]*|проголосовавш[а-яё]*|поддержавш[а-яё]*)\b|"
    r"\b(?:из\s+них|в\s+том\s+числе|от\s+общего|от\s+всех|абсолютн[а-яё]*\s+процентн[а-яё]*\s+пункт[а-яё]*)\b", re.I)
NUMERIC_APPROXIMATION = re.compile(
    r"\b(?:около|примерно|порядка|почти|свыше|менее|более|до|не\s+более|не\s+менее)\s*$", re.I)


def _numeric_clauses(value):
    """Bounded same-sentence relations; decimals and count abbreviations survive."""
    start = 0
    for boundary in re.finditer(r"[.!?;\r\n]", value):
        at = boundary.start()
        if boundary[0] == "." and (
                (at and at + 1 < len(value) and value[at - 1].isdigit() and value[at + 1].isdigit())
                or re.search(r"\b(?:тыс|млн|млрд|г)$", value[max(0, at - 5):at], re.I)):
            continue
        if 0 < at - start <= 800:
            yield start, value[start:at]
        start = boundary.end()
    if 0 < len(value) - start <= 800:
        yield start, value[start:]


def _number(value, scale="", exact=False):
    """Exact decimal arithmetic with conservative reported-precision intervals."""
    value = re.sub(r"[ \u00a0\u202f]", "", value).replace(",", ".")
    if len(value) > 18 or re.fullmatch(r"[1-9][0-9]{0,2}\.[0-9]{3}", value):
        # 1,000 / 1.000 can be either a decimal or a foreign thousands group.
        return None
    amount = Decimal(value)
    factor = (Decimal(1000) if scale.lower().startswith("тыс") else
              Decimal(1000000) if scale.lower().startswith(("млн", "миллион")) else
              Decimal(1000000000) if scale else Decimal(1))
    amount *= factor
    if not 0 <= amount <= 10 ** 15:
        return None
    if "." in value:
        resolution = Decimal(1).scaleb(-len(value.split(".")[1]))
    else:
        # News commonly round 100/10000 to the last nonzero digit. Accept that
        # uncertainty rather than treating every written integer as exact.
        resolution = Decimal(10) ** (len(value) - len(value.rstrip("0"))) if amount else Decimal(1)
    radius = Decimal(0) if exact else resolution * factor / 2
    return amount, max(Decimal(0), amount - radius), amount + radius


def _number_text(value):
    result = format(value, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _metric_key(value):
    words = value.casefold().replace("ё", "е").split()
    if any(re.fullmatch(NUMERIC_SCALE, word, re.I) for word in words):
        return ""  # An unlabelled '100 thousand per day' is not a known metric.
    aliases = {"событие": "событий", "события": "событий", "авария": "аварий", "аварии": "аварий",
               "случай": "случаев", "случая": "случаев", "человек": "человек", "человека": "человек",
               "людей": "человек", "рубль": "рублей", "рубля": "рублей"}
    return " ".join(aliases.get(word, word) for word in words)


def _numeric_signals(value):
    """Book-inspired, local consistency questions, not verification of statistics."""
    if not re.search(r"[0-9]", value):
        return
    for offset, clause in _numeric_clauses(value):
        if not NUMERIC_SCOPE_GUARD.search(clause) and clause.count("%") == 1:
            for pattern in (MAJORITY_FORWARD, MAJORITY_REVERSE):
                for match in pattern.finditer(clause):
                    prefix = clause[max(0, match.start() - 45):match.start()]
                    if (re.search(r"\bне\s+(?:(?:абсолютное|подавляющее)\s+)?$", prefix, re.I)
                            or NUMERIC_APPROXIMATION.search(prefix)
                            or re.search(r"[-−]\s*$", prefix)
                            or re.search(r"\b(?:около|примерно|порядка|почти|свыше|менее|более)\b", match["group"], re.I)):
                        continue
                    numbers = [Decimal(n.replace(",", ".")) for n in re.findall(
                        r"[0-9]+(?:[.,][0-9]+)?", match["percent"])]
                    if (not numbers or not all(0 <= n < 50 for n in numbers)
                            or (len(numbers) == 2 and numbers[0] > numbers[1])
                            or (len(numbers) == 1 and match["percent"].lower().startswith("от"))):
                        continue
                    # A percentage may describe an outcome within a majority,
                    # or another denominator. Keep only direct, simple links.
                    group = match["group"].strip(" ,«»\"")
                    if (re.search(r"\b(?:из|среди|котор[а-яё]*|состав[а-яё]*)\b", group, re.I)
                            or re.search(r"\b[а-яё]+(?:ли|ло|лся|лась|лось|лись|ют|ут|ет|ит)\b", group, re.I)):
                        continue
                    tail = clause[match.end():].split(",", 1)[0][:80]
                    before_groups = NUMERIC_GROUP.findall(group.lower())
                    after_groups = NUMERIC_GROUP.findall(tail.lower())
                    if (after_groups and group and before_groups != after_groups
                            or re.search(r"\b(?:рост[а-яё]*|прирост[а-яё]*|снижен[а-яё]*|увеличен[а-яё]*)\b", tail, re.I)):
                        continue
                    start, end = match.span()
                    if "(" in match[0] and clause[end:end + 1] == ")":
                        end += 1
                    yield {"rule_id": "context.majority_percentage", "label": "Большинство и процент",
                           "spans": [(offset + start, offset + end)],
                           "observations": {"majority_percentage_check": True,
                                            "stated_percent": match["percent"], "truth_checked": False},
                           "detail": " Указано: «" + clause[start:end].strip() + "»."}

        # A per-day rate and a year total need the same named measure and an
        # explicit conversion/total link. Never combine arbitrary nearby numbers.
        if (re.search(r"\b(?:сезон[а-яё]*|месяц[а-яё]*|недел[а-яё]*|"
                      r"январ[а-яё]*|феврал[а-яё]*|март[а-яё]*|апрел[а-яё]*|ма[йяе]|июн[а-яё]*|июл[а-яё]*|"
                      r"август[а-яё]*|сентябр[а-яё]*|октябр[а-яё]*|ноябр[а-яё]*|декабр[а-яё]*|"
                      r"сегодня|вчера|пик[а-яё]*|прогноз[а-яё]*|максим[а-яё]*|миним[а-яё]*)\b", clause, re.I)
                or re.search(r"\b(?:рабоч|учебн|торгов)[а-яё]*\s+(?:день|дня|дни|дней|сут[а-яё]*)\b", clause, re.I)
                or re.search(r"\b(?:19|20)[0-9]{2}\s*(?:[-–—]|по|и)\s*(?:19|20)[0-9]{2}\b", clause)):
            continue
        days = [365, 366]
        years = set(re.findall(r"\b((?:19|20)[0-9]{2})\s*(?:год[а-яё]*\b|г\.)", clause, re.I))
        if len(years) > 1:
            continue
        if years:
            days = [366 if calendar.isleap(int(next(iter(years)))) else 365]
        daily = list(DAILY_NUMBER.finditer(clause))
        annual = list(ANNUAL_NUMBER.finditer(clause))
        if len(daily) != 1 or len(annual) != 1:
            continue
        rate, total = daily[0], annual[0]
        if re.match(r"\s+(?:в|на|по|среди|для|у|при)\b", clause[total.end():], re.I):
            # A trailing population/location may narrow only the annual count.
            # Do not infer that 'per year in another country' shares the rate's scope.
            continue
        if (rate.end() >= total.start() or total["metric"] and
                _metric_key(rate["metric"]) != _metric_key(total["metric"])):
            continue
        if not _metric_key(rate["metric"]):
            continue
        link = clause[rate.end():total.start()]
        if not (re.fullmatch(r"\s*[—–=:]\s*", link)
                or re.fullmatch(r"[\s,():—–-]*(?:(?:а\s+)?(?:всего|итого|то\s+есть|или|следовательно|"
                                r"значит|получается|это|суммарно|ровно|точно|что\s+составляет)\b[\s,:—–-]*)+", link, re.I)):
            continue
        # Different named/deictic periods, exclusions and bounded/approximate
        # rates are deliberately left to a human, not annualised as constants.
        if (re.search(r"\b(?:летом|зимой|осенью|весной|сейчас|прошл[а-яё]*|предыдущ[а-яё]*|"
                      r"текущ[а-яё]*|нынешн[а-яё]*|следующ[а-яё]*|кроме|исключая|выходн[а-яё]*)\b", clause, re.I)
                or any(NUMERIC_APPROXIMATION.search(clause[max(0, m.start() - 35):m.start()])
                       or re.search(r"(?:[+−-]|\bна|[0-9][ \u00a0\u202f]+)\s*$", clause[max(0, m.start() - 35):m.start()])
                       for m in (rate, total))):
            continue
        parsed = []
        for m in (rate, total):
            exact = bool(re.search(r"\b(?:ровно|точно)\s*$", clause[max(0, m.start() - 20):m.start()], re.I))
            parsed.append(_number(m["number"], m["scale"] or "", exact))
        if not all(parsed):
            continue
        rate_number, total_number = parsed
        expected_low, expected_high = rate_number[1] * min(days), rate_number[2] * max(days)
        if expected_low <= total_number[2] and total_number[1] <= expected_high:
            continue
        nominal = [_number_text(rate_number[0] * d) for d in days]
        yield {"rule_id": "context.daily_year_total", "label": "Суточное число и годовой итог",
               "spans": [(offset + m.start(), offset + m.end()) for m in (rate, total)],
               "observations": {"daily_year_check": True, "days_considered": days,
                                "daily_number": _number_text(rate_number[0]),
                                "stated_annual": _number_text(total_number[0]),
                                "nominal_annual": nominal, "rounding_intervals_overlap": False,
                                "annual_metric_inherited": not bool(total["metric"]),
                                "expected_annual_interval": [_number_text(expected_low), _number_text(expected_high)],
                                "truth_checked": False},
               "detail": (" При буквальном пересчёте: " + _number_text(rate_number[0]) + " в день → "
                          + "–".join(dict.fromkeys(nominal)) + " в год; указано "
                          + _number_text(total_number[0]) + ".")}


def _literature_notices(title, text, quotes):
    """Observable numeric/commercial/repetition cues, never fact-check verdicts.

    Search both complete input fields for an identifiable quantitative basis,
    rather than mistaking a shortened display excerpt for the whole document.
    Publisher identity, URL and publication date never supply or remove a cue.
    """
    values = {"title": title, "text": text}
    combined = title + "\n" + text

    def notice(rule_id, label, spans, **observations):
        rule = LITERATURE_NOTICES[rule_id]
        evidence = []
        for field, start, end in spans:
            item = _evidence(field, values[field], start, end, quotes[field])
            item["context"].update(informational_notice=True, **observations)
            evidence.append(item)
        return {"rule_id": rule.id, "category": rule.category, "label": label,
                "status": "context_only", "explanation": rule.explanation,
                "review_question": rule.review_question, "evidence": evidence}

    survey_basis = re.search(
        r"\b(?:выборк[а-яё]*|методик[а-яё]*|анкет[а-яё]*|ВЦИОМ|ФОМ|Росстат|Gallup)\b|"
        r"\b\d[\d\s]{0,10}\s+(?:респондент[а-яё]*|опрошенн[а-яё]*|участник[а-яё]*)\b|"
        r"\bпо\s+(?:данным|результатам)\s+(?:опроса|исследования)\b", combined, re.I,
    )
    absolute_basis = re.search(
        r"\b(?:с|от)\s+\d+(?:[.,]\d+)?\s*%?\s+до\s+\d+(?:[.,]\d+)?\s*%?|"
        r"\b\d+\s+из\s+\d+\b|\bодин\s+случай\s+из\s+\d+\b|"
        r"\b(?:исходн[а-яё]*|абсолютн[а-яё]*|базов[а-яё]*)\s+(?:риск[а-яё]*|уров[а-яё]*)\b",
        combined, re.I,
    )
    for field, value in values.items():
        for signal in _numeric_signals(value):
            finding = notice(signal["rule_id"], signal["label"],
                             [(field, start, end) for start, end in signal["spans"]], **signal["observations"])
            finding["explanation"] += signal["detail"]
            yield finding
        if not survey_basis:
            for match in re.finditer(
                r"\b\d{1,3}(?:[.,]\d{1,3})?\s*%\s+(?:жител[а-яё]*|граждан[а-яё]*|избирател[а-яё]*|"
                r"россиян[а-яё]*|опрошенн[а-яё]*)\s+(?:[а-яё-]+\s+){0,2}"
                r"(?:поддерж[а-яё]*|одобр[а-яё]*|выбра[а-яё]*|предпоч[а-яё]*|проголос[а-яё]*)\b", value, re.I,
            ):
                percent = float(re.match(r"\d+(?:[.,]\d+)?", match[0])[0].replace(",", "."))
                if percent <= 100:
                    yield notice("context.percent_basis", "Основание процентной оценки",
                                 [(field, *match.span())], quantitative_basis_not_recognized=True,
                                 full_input_checked=True, truth_checked=False)
        if not absolute_basis:
            for match in re.finditer(
                r"\bриск\s+(?:вырос|увеличился|снизился|сократился)\s+на\s+\d+(?:[.,]\d+)?\s*%", value, re.I,
            ):
                yield notice("context.relative_risk_basis", "Относительное изменение риска",
                             [(field, *match.span())], absolute_basis_not_recognized=True,
                             full_input_checked=True, truth_checked=False)
        for match in re.finditer(
            r"\b(?:запишитесь|записывайтесь|купите|закажите|покупайте|успейте\s+купить)\b"
            r"[^.!?\n]{0,160}\bпо\s+промокоду\s+[\w-]{2,40}\b", value, re.I,
        ):
            yield notice("context.commercial_call", "Коммерческий призыв",
                         [(field, *match.span())], commercial_cue=True,
                         hidden_payment_established=False)

    # Sentence equality is deliberately narrower than semantic similarity.
    # No title/body duplicates; only public evaluative theses in >=3 paragraphs.
    if re.search(r"\b(?:учебн[а-яё]*\s+пример|разбор\s+повтор[а-яё]*|обсуждени[а-яё]*\s+лозунг[а-яё]*|"
                 r"в\s+(?:романе|фильме|спектакле))\b",
                 title + "\n" + text[:400], re.I):
        return
    paragraph_starts = [0] + [match.end() for match in re.finditer(r"\n+", text)]
    repeated = {}
    for segment in re.finditer(r"[^.!?\n]+", text):
        words = []
        for word in re.finditer(r"[а-яё]+(?:-[а-яё]+)*", segment[0], re.I):
            words.append(word)
            if len(words) > 12:
                break
        if not 4 <= len(words) <= 12:
            continue
        phrase = segment[0]
        if (not re.search(r"\b(?:закон[а-яё]*|партия|правительств[а-яё]*|власт[а-яё]*|страна|народ)\b", phrase, re.I)
                or not re.search(r"\b(?:верн[её]т[а-яё]*|принес[её]т[а-яё]*|обеспеч[а-яё]*|досто[йи]н[а-яё]*|"
                                 r"поддерж[а-яё]*|защит[а-яё]*|спас[а-яё]*)\b", phrase, re.I)):
            continue
        start, end = segment.start() + words[0].start(), segment.start() + words[-1].end()
        canonical = tuple(word[0].casefold().replace("ё", "е") for word in words)
        paragraph = bisect_right(paragraph_starts, start) - 1
        group = repeated.setdefault(canonical, {"spans": [], "last_paragraph": -1, "paragraphs": 0, "occurrences": 0})
        group["occurrences"] += 1
        if paragraph != group["last_paragraph"]:
            group["last_paragraph"] = paragraph
            group["paragraphs"] += 1
            if len(group["spans"]) < 3:
                group["spans"].append(("text", start, end))
    for group in repeated.values():
        if group["paragraphs"] >= 3:
            yield notice("context.repeated_thesis", "Повторение тезиса", group["spans"],
                         repeated_thesis=True, occurrences=group["occurrences"],
                         distinct_paragraphs=group["paragraphs"], semantic_similarity_used=False)


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
                        "rule_id": rule.id, "category": rule.category, "label": RULE_LABELS.get(rule.id, LABELS[rule.category]),
                        "status": "context_only" if rule.id == "context.quotation_omission" or rule.category in INFORMATIONAL else _status(evidence),
                        "explanation": rule.explanation,
                        "review_question": rule.review_question, "evidence": [evidence],
                    })
        if informational:
            for notices in (_rhetorical_notices(title, text, quotes, findings,
                                               document.get("media", {}).get("image_count", 0)),
                            _literature_notices(title, text, quotes)):
                for finding in notices:
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

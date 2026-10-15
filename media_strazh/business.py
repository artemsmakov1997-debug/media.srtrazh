"""Bounded public business evidence, without full article bodies or private profiles."""

from datetime import datetime, timedelta, timezone
import json
from itertools import chain
import re
import unicodedata

from .sources import SOURCES, normalize_url
from .storage import utcnow

SCHEMA = "business-evidence-1.0"
MAX_RECORDS = 5000
MAX_BYTES = 8_000_000
MAX_NAMES = 512
WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*", re.UNICODE)
LEGAL = {"ооо", "пао", "ао", "оао", "зао", "нко", "ип", "llc", "inc", "ltd"}
WATCHLISTS = [{"id": "mc21", "name": "Медицинский центр «XXI век»", "url": "https://mc21.ru/",
              "aliases": ["Медицинский центр XXI век", "МЦ XXI век", "Клиника XXI век",
                          "XXI век", "21 век", "XXIвек", "21век", "Медицинский центр 21 век", "Медцентр XXI век", "mc21.ru"]}]
CENTURY_BRAND = r"(?:XXI|21)\s*[-–]?\s*век"
MEDICAL_BRAND = re.compile(r"\b(?:медицинск[а-яё]*\s+центр[а-яё]*|медцентр[а-яё]*|"
                           r"клиник[а-яё]*|МЦ)\s*[«\"“]?\s*" + CENTURY_BRAND + r"\b", re.I)
QUOTED_BRAND = re.compile(r"[«\"“]\s*" + CENTURY_BRAND + r"\s*[»\"”]", re.I)
OTHER_NAMED_OBJECT = re.compile(r"\b(?:книг[а-яё]*|журнал[а-яё]*|газет[а-яё]*|роман[а-яё]*|"
                                r"выставк[а-яё]*|конференци[а-яё]*|торгов[а-яё]*\s+центр[а-яё]*)\s*$", re.I)
MEDICAL_CONTEXT = re.compile(r"\b(?:медицинск[а-яё]*|клиник[а-яё]*|медцентр[а-яё]*|"
                             r"пациент[а-яё]*|лечени[а-яё]*|врач[а-яё]*)\b", re.I)


def watchlist_matches(value):
    domain = re.search(r"(?<![\w.-])(?:https?://)?(?:www\.)?mc21\.ru(?![\w.-])", value, re.I)
    match = MEDICAL_BRAND.search(value)
    if not domain and not match:
        match = next((m for m in QUOTED_BRAND.finditer(value)
                      if MEDICAL_CONTEXT.search(value[max(0, m.start() - 160):m.end() + 160])
                      and not OTHER_NAMED_OBJECT.search(value[max(0, m.start() - 70):m.start()])), None)
    return (["mc21"], (domain or match).start()) if domain or match else ([], None)

# Topic membership is a reproducible keyword match, not an inferred trend or
# sentiment. Counts always refer to the retained sample of publications.
TOPICS = {
    "medtech": [
        ("equipment", "Медицинское оборудование", r"медицинск[а-яё]*\s+(?:оборудован|техник)|медоборудован|томограф|рентген|медиздел"),
        ("health", "Организация здравоохранения", r"здравоохранен|больниц|поликлиник|клиник|медицинск[а-яё]*\s+центр|медцентр|пациент|врач"),
        ("regulation", "Регулирование медицинского рынка", r"росздравнадзор|регистраци[а-яё]*\s+мед|маркировк[а-яё]*\s+лекарств"),
        ("innovation", "Медицинские исследования и технологии", r"медицинск[а-яё]*\s+технолог|клиническ[а-яё]*\s+исследован|диагностик"),
    ],
    "industry": [
        ("production", "Промышленное производство", r"промышленн|производственн|завод[а-яё]*|станкостро"),
        ("supply", "Поставки и логистика", r"логистик|цепочк[а-яё]*\s+постав|импортозамещ|локализаци[а-яё]*\s+производ"),
        ("technology", "Технологии и автоматизация", r"роботизац|автоматизац|промышленн[а-яё]*\s+технолог"),
        ("staff", "Кадры на производстве", r"инженер|рабоч[а-яё]*\s+специальност|дефицит[а-яё]*\s+кадр"),
    ],
    "hospitality": [
        ("hotels", "Гостиницы и размещение", r"гостиниц|\bотел(?:ь|я|ю|е|и|ей|ям|ями|ях)\b|средств[а-яё]*\s+размещен"),
        ("travel", "Туризм и поездки", r"туризм|турист|путешеств|командиров"),
        ("food", "Гастрономия и ресторанный рынок", r"ресторан|гастроном|общественн[а-яё]*\s+питан"),
        ("service", "Гостиничный сервис", r"гостиничн[а-яё]*\s+сервис|обслуживани[а-яё]*\s+гост|pet[- ]friendly"),
    ],
}
COMPILED_TOPICS = [(industry + ":" + key, re.compile(pattern, re.I))
                   for industry, topics in TOPICS.items() for key, _, pattern in topics]


def normalize_name(value):
    words = re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", value).casefold().replace("ё", "е"))
    while words and words[0] in LEGAL:
        words.pop(0)
    while words and words[-1] in LEGAL:
        words.pop()
    return " ".join(words)


def name_candidates(title, text):
    """Public name-like spans: quoted names, uppercase tokens and proper-name runs.

    This is deliberately not a full-text dump or a complete entity recognizer.
    Lowercase unquoted Russian brands and homonyms require manual verification.
    """
    names = set()

    def add(value):
        value = normalize_name(value)
        if 2 <= len(value) <= 100 and any(c.isalpha() for c in value):
            names.add(value)

    for value in (title, text):
        value = re.sub(r"https?://\S+", " ", value)
        for match in re.finditer(r'[«“"]([^»”"\n]{2,100})[»”"]', value):
            if len(WORD.findall(match[1])) <= 6:
                add(match[1])
        tokens = list(WORD.finditer(value))
        for index, token in enumerate(tokens):
            word = token.group()
            if len(word) < 2 or not (word[0].isupper() or re.search(r"[a-zA-Z]", word)):
                continue
            add(word)
            end = token.end()
            for next_token in tokens[index + 1:index + 6]:
                gap = value[end:next_token.start()]
                if not gap.isspace() or not next_token.group()[0].isupper():
                    break
                add(value[token.start():next_token.end()])
                end = next_token.end()
    ordered = sorted(names, key=lambda name: (len(name.split()), name))
    return ordered[:MAX_NAMES], len(ordered) > MAX_NAMES


def business_snapshot(store, now=None):
    stamp = now or utcnow()
    end = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc)
    start = (end - timedelta(days=180)).isoformat()
    placeholders = ",".join("?" for _ in SOURCES)
    base = """FROM articles a JOIN revisions r ON r.id=a.current_revision_id
              WHERE a.source_id IN (""" + placeholders + ")"
    args = list(SOURCES)
    scope = " AND julianday(r.published_at) >= julianday(?) AND julianday(r.published_at) <= julianday(?)"
    store.db.execute("SAVEPOINT business_snapshot")
    try:
        corpus_total = store.db.execute("SELECT COUNT(*) " + base, args).fetchone()[0]
        undated = store.db.execute("SELECT COUNT(*) " + base + " AND julianday(r.published_at) IS NULL", args).fetchone()[0]
        eligible = store.db.execute("SELECT COUNT(*) " + base + scope, [*args, start, stamp]).fetchone()[0]
        first_collected = store.db.execute("SELECT MIN(a.first_seen_at) " + base, args).fetchone()[0]
        query = "SELECT a.id,a.source_id,r.canonical_url AS url,r.title,r.text,r.published_at,r.retrieved_at,julianday(r.published_at) AS sort_at "
        order = " ORDER BY julianday(r.published_at) DESC,a.id DESC"
        # A rare tracked company must not lose an older mention merely because
        # thousands of newer, unrelated political posts fill the public sample.
        likely = " AND (r.title LIKE '%XXI%' OR r.text LIKE '%XXI%' OR r.title LIKE '%21%' OR r.text LIKE '%21%')"
        priority = store.db.execute(query + base + scope + likely + order, [*args, start, stamp])
        priority = (row for row in priority if watchlist_matches(row["title"] + "\n" + row["text"])[0])
        newest = store.db.execute(query + base + scope + order, [*args, start, stamp])
        records, size, seen, seen_ids, duplicate_count = [], 0, set(), set(), 0
        sort_keys = {}
        limited = eligible > MAX_RECORDS
        for row in chain(priority, newest):
            if row["id"] in seen_ids:
                continue
            seen_ids.add(row["id"])
            if len(records) >= MAX_RECORDS:
                limited = True
                break
            source = SOURCES[row["source_id"]]
            url = normalize_url(row["url"], source)
            if url in seen:
                duplicate_count += 1
                continue
            seen.add(url)
            names, truncated = name_candidates(row["title"], row["text"])
            value = row["title"] + "\n" + row["text"]
            entities, match_at = watchlist_matches(value)
            excerpt = " ".join(value[max(0, match_at - 120):match_at + 220].split()) if match_at is not None else " ".join(row["text"].split())[:320]
            record = {
                "id": row["id"], "source_id": source.id, "source": source.name,
                "publisher_id": source.publisher, "platform": source.platform,
                "url": url, "title": row["title"][:500],
                "excerpt": excerpt, "watchlists": entities,
                "published_at": row["published_at"], "retrieved_at": row["retrieved_at"],
                "names": names, "names_truncated": truncated,
                "topics": [key for key, pattern in COMPILED_TOPICS if pattern.search(value)],
            }
            amount = len(json.dumps(record, ensure_ascii=False).encode("utf-8"))
            if size + amount > MAX_BYTES:
                limited = True
                break
            size += amount
            records.append(record)
            sort_keys[row["id"]] = (row["sort_at"], row["id"])
        records.sort(key=lambda record: sort_keys[record["id"]], reverse=True)
        status = store.status()
        return {
            "schema_version": SCHEMA, "generated_at": stamp,
            "coverage": {"corpus_total": corpus_total, "eligible": eligible, "published": len(records),
                         "undated_excluded": undated, "limited": limited, "duplicates_excluded": duplicate_count,
                         "publication_sources": len({row["source_id"] for row in records}),
                         "first_collected_at": first_collected,
                         "name_indices_limited": sum(row["names_truncated"] for row in records),
                         "window_start": start, "window_end": stamp},
            "sources": [{"id": source.id, "name": source.name,
                         "last_success_at": next((s["last_success_at"] for s in status["sources"] if s["source_id"] == source.id), None)}
                        for source in SOURCES.values()],
            "topic_definitions": {key: [{"id": key + ":" + code, "title": title} for code, title, _ in topics]
                                  for key, topics in TOPICS.items()},
            "watchlists": WATCHLISTS,
            "articles": records,
        }
    finally:
        store.db.execute("RELEASE business_snapshot")

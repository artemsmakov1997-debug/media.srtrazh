"""Corpus report for the trigger lexicon: rating impact, review sample, new candidates.

Runs the current analyser over the retained corpus once. Older findings are the
result without ``lex.*`` findings (the lexicon runs after hand-written rules and
never suppresses them), so the "before" share needs no second pass.

Candidates are *suggestions for a human*, never added automatically:
- ``productive``: word forms built like known labels (укро-…, рус-о-…, …-изм,
  страна-…) that no current rule matches;
- ``near_triggers``: word stems over-represented in sentences that already
  contain a manipulation marker, compared with the whole corpus (log-odds).
"""

from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import random
import re

from .analysis import INFORMATIONAL, VERSION, analyze
from .crossposts import current_publications
from .lexicon import LEXICON_VERSION
from .rating import publication_types
from .sources import SOURCES

WORD = re.compile(r"[а-яё]+(?:-[а-яё]+)*", re.I)
ENDINGS = sorted((
    "ами ями ого его ому ему ыми ими ией иям иях ов ев ей ам ям ах ях ом ем ой ая яя ое ее ые ие ую юю ых их "
    "ым им ою ею а я о е ы и у ю ь й").split(), key=len, reverse=True)
STOP = set((
    "и в во не что он на я с со как а то все она так его но да ты к у же вы за бы по только ее её мне было вот от "
    "меня еще ещё нет о из ему теперь когда даже ну вдруг ли если уже или ни быть был него до вас нибудь опять уж "
    "вам ведь там потом себя ничего ей может они тут где есть надо ней для мы тебя их чем была сам чтоб без будто "
    "чего раз тоже себе под будет ж тогда кто этот того потому этого какой совсем ним здесь этом один почти мой тем "
    "чтобы нее сейчас были куда зачем всех никогда можно при наконец два об другой хоть после над больше тот через "
    "эти нас про всего них какая много разве три эту моя впрочем хорошо свою этой перед иногда лучше чуть том нельзя "
    "такой им более всегда конечно всю между это также который которые которых году года заявил заявила сообщил "
    "сообщила отметил отметила словам время также ранее сообщает пишет глава россии рф сша украины").split())
PRODUCTIVE = re.compile(
    r"(?<![а-яё])(?:"
    r"(?:укр|рус|рос|раш|пут|зел|кремл|либер|ват|амер|евр|гей|пинд|хох|кацап|бандер|киев|моск|запад|"
    r"демшиз|соросят|навальн|z|зет)[а-яё]*(?:ист|изм|оид|ня|ят|ец|цы|ия|лог|аст|ота|нут|бот|ушк|ина)[а-яё]{0,3}"
    r"|[а-яё]{3,}[-‑](?:террорист|агрессор|изго[йяи]|бензоколонк|фашист|нацист|колони|марионетк)[а-яё]*"
    r"|(?:укро|русо|рашо|кремле|евро|пиндо|гейро|либеро|нацио)[-‑]?[а-яё]{4,}"
    r")(?![а-яё])", re.I)
MANIPULATION = {"needs_review", "quoted_candidate"}


def stem(word):
    word = word.casefold().replace("ё", "е")
    for ending in ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= 4:
            return word[:-len(ending)]
    return word


def _covered(word):
    """True when any current rule already marks this word in a public sentence."""
    probe = f"{word} — так их назвали в Кремле и в Киеве."
    return any(e["field"] == "text" and e["start"] < len(word)
               for f in analyze({"text": probe})["findings"] for e in f["evidence"])


def corpus_report(store, top=300, samples=200, seed=2026):
    rows = [row for row in current_publications(store) if row["text"] and row["text"].strip()]
    rng = random.Random(seed)
    publishers = defaultdict(lambda: {"documents": 0, "flagged_before": 0, "flagged_after": 0,
                                      "lexicon_only": 0, "groups": Counter()})
    groups, hits = Counter(), []
    doc_stems, window_stems, examples = Counter(), Counter(), {}
    productive, productive_examples = Counter(), {}
    marked_docs = 0
    for row in rows:
        document = {"title": row["title"] or "", "text": row["text"]}
        try:
            findings = analyze(document)["findings"]
        except ValueError:
            continue
        publisher = SOURCES[row["source_id"]].publisher if row["source_id"] in SOURCES else row["source_id"]
        item = publishers[publisher]
        before = publication_types([f for f in findings if not f["rule_id"].startswith("lex.")])
        after = publication_types(findings)
        item["documents"] += 1
        item["flagged_before"] += bool(before)
        item["flagged_after"] += bool(after)
        item["lexicon_only"] += bool(after) and not before
        for finding in findings:
            if finding["rule_id"].startswith("lex."):
                groups[finding["rule_id"]] += 1
                item["groups"][finding["rule_id"]] += 1
                evidence = finding["evidence"][0]
                hits.append({"group": finding["rule_id"], "status": finding["status"], "quote": evidence["quote"],
                             "sentence": evidence["sentence"]["text"].strip()[:400], "source": row["source_id"],
                             "url": row.get("url", "")})
        full = document["title"] + "\n" + document["text"]
        stems = {stem(word) for word in WORD.findall(full) if len(word) > 3 and word.casefold() not in STOP}
        doc_stems.update(stems)
        near = set()
        for finding in findings:
            if finding["category"] in INFORMATIONAL or finding["status"] not in MANIPULATION:
                continue
            for evidence in finding["evidence"]:
                sentence = evidence["sentence"]["text"]
                quote = evidence["quote"].casefold()
                for word in WORD.findall(sentence):
                    if len(word) > 3 and word.casefold() not in STOP and word.casefold() not in quote:
                        key = stem(word)
                        near.add(key)
                        examples.setdefault(key, (word, sentence.strip()[:300], row["source_id"]))
        if near:
            marked_docs += 1
            window_stems.update(near)
        for match in PRODUCTIVE.finditer(full):
            key = match.group(0).casefold().replace("ё", "е")
            productive[key] += 1
            productive_examples.setdefault(key, (match.group(0), full[max(0, match.start() - 120):match.end() + 120]
                                                 .replace("\n", " ").strip(), row["source_id"]))

    total = len(rows) or 1
    scored = []
    for key, inside in window_stems.items():
        if inside < 3:
            continue
        overall = doc_stems[key]
        # Smoothed log-odds of a stem in marked sentences vs the whole corpus.
        score = (math.log((inside + 0.5) / (marked_docs - inside + 1)) -
                 math.log((overall + 0.5) / (total - overall + 1)))
        scored.append((score, inside, overall, key))
    scored.sort(reverse=True)
    near_candidates = []
    for score, inside, overall, key in scored:
        word, sentence, source = examples[key]
        if _covered(word):
            continue
        near_candidates.append({"stem": key, "example_word": word, "score": round(score, 3),
                                "docs_near_markers": inside, "docs_total": overall,
                                "example": sentence, "source": source})
        if len(near_candidates) >= top:
            break
    productive_candidates = []
    for key, count in productive.most_common():
        word, context, source = productive_examples[key]
        if _covered(word):
            continue
        productive_candidates.append({"word": word, "documents": count, "example": context, "source": source})
        if len(productive_candidates) >= top:
            break

    rated = []
    for publisher, item in sorted(publishers.items()):
        documents = item["documents"] or 1
        rated.append({"publisher": publisher, "documents": item["documents"],
                      "share_before": round(100 * item["flagged_before"] / documents, 1),
                      "share_after": round(100 * item["flagged_after"] / documents, 1),
                      "lexicon_only": item["lexicon_only"], "top_groups": dict(item["groups"].most_common(5))})
    rng.shuffle(hits)
    return {
        "schema_version": "lexicon-report-1.0", "algorithm_version": VERSION, "lexicon_version": LEXICON_VERSION,
        "documents": len(rows), "documents_with_markers": marked_docs,
        "share_note": "Доли за весь сохранённый корпус, а не за 24 часа; «до» — результат без словаря lex.*.",
        "publishers": rated, "groups": dict(groups.most_common()),
        "review_sample": hits[:samples],
        "candidates": {"productive": productive_candidates, "near_triggers": near_candidates},
    }


def write_report(report, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "lexicon-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    tables = {
        "publishers.csv": (report["publishers"], ("publisher", "documents", "share_before", "share_after", "lexicon_only")),
        "review-sample.csv": (report["review_sample"], ("group", "status", "quote", "sentence", "source", "url")),
        "candidates-productive.csv": (report["candidates"]["productive"], ("word", "documents", "example", "source")),
        "candidates-near-triggers.csv": (report["candidates"]["near_triggers"],
                                         ("example_word", "stem", "score", "docs_near_markers", "docs_total", "example", "source")),
    }
    for name, (rows, columns) in tables.items():
        # UTF-8 with BOM opens correctly in Excel; extra keys are ignored.
        with (output / name).open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    return {"output": str(output), "files": ["lexicon-report.json", *tables],
            "documents": report["documents"], "groups": len(report["groups"]),
            "candidates": {key: len(value) for key, value in report["candidates"].items()}}


def summary_markdown(report, candidates=40, samples=40):
    """Readable job summary: visible on the Actions page without the artifact."""
    def cell(value):
        return str(value).replace("|", "/").replace("\n", " ")
    lines = [f"## Отчёт по словарю {report['lexicon_version']} ({report['algorithm_version']})", "",
             f"Публикаций в корпусе: {report['documents']}. {report['share_note']}", "",
             "| СМИ | Публикаций | До, % | После, % | Добавил словарь |", "| --- | ---: | ---: | ---: | ---: |"]
    for item in sorted(report["publishers"], key=lambda item: -item["documents"]):
        lines.append(f"| {item['publisher']} | {item['documents']} | {item['share_before']} | "
                     f"{item['share_after']} | {item['lexicon_only']} |")
    lines += ["", "### Срабатывания по группам", "", "| Группа | Число |", "| --- | ---: |"]
    lines += [f"| {key} | {value} |" for key, value in report["groups"].items()]
    lines += ["", "### Случайная выборка срабатываний", "", "| Группа | Статус | Фрагмент | Предложение | Источник |",
              "| --- | --- | --- | --- | --- |"]
    lines += [f"| {cell(hit['group'])} | {hit['status']} | {cell(hit['quote'])} | {cell(hit['sentence'][:220])} | {hit['source']} |"
              for hit in report["review_sample"][:samples]]
    lines += ["", "### Кандидаты: построены как ярлыки", "", "| Слово | Публикаций | Пример |", "| --- | ---: | --- |"]
    lines += [f"| {cell(item['word'])} | {item['documents']} | {cell(item['example'][:200])} |"
              for item in report["candidates"]["productive"][:candidates]]
    lines += ["", "### Кандидаты: часто рядом с маркерами", "", "| Слово | Оценка | Рядом с маркерами | Всего | Пример |",
              "| --- | ---: | ---: | ---: | --- |"]
    lines += [f"| {cell(item['example_word'])} | {item['score']} | {item['docs_near_markers']} | {item['docs_total']} | "
              f"{cell(item['example'][:200])} |" for item in report["candidates"]["near_triggers"][:candidates]]
    return "\n".join(lines) + "\n"

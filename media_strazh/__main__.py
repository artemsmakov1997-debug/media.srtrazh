import argparse
import json
from pathlib import Path
import sqlite3
import sys

from .analysis import analyze
from .evaluation import evaluate
from .publishing import build_site
from .server import serve
from .collector import collect_once, reanalyze_current, reextract_current, selected_sources, watch
from .storage import DEFAULT_DB, Store, collection_lock, utcnow


def main():
    parser = argparse.ArgumentParser(description="МЕДИА.СТРАЖ: анализ признаков в русскоязычных новостях")
    commands = parser.add_subparsers(dest="command", required=True)
    article = commands.add_parser("analyze", help="Проанализировать текст из файла или stdin")
    article.add_argument("--file", type=Path, help="UTF-8 текст статьи; иначе используется stdin")
    article.add_argument("--title", default="")
    article.add_argument("--source", default="")
    web = commands.add_parser("serve", help="Запустить локальный API и форму анализа")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", type=int, default=8001)
    web.add_argument("--db", type=Path, default=DEFAULT_DB)
    evaluation = commands.add_parser("evaluate", help="Оценить кандидатов на полностью размеченном JSONL")
    evaluation.add_argument("--file", type=Path, required=True)
    for name, description in (("collect", "Собрать и проанализировать новости один раз"),
                              ("watch", "Проверять ленты и анализировать новости по расписанию")):
        collection = commands.add_parser(name, help=description)
        collection.add_argument("--db", type=Path, default=DEFAULT_DB)
        collection.add_argument("--source", action="append", choices=["rt", "tass", "ria"],
                                help="Повторите для нескольких источников; по умолчанию все три")
        collection.add_argument("--feed", action="append", metavar="ID=HTTPS_URL",
                                help="Заменить URL RSS на том же домене")
        collection.add_argument("--limit", type=int, default=5, help="Максимум загрузок на источник за цикл")
        collection.add_argument("--revisit-seconds", type=int, default=3600)
        if name == "watch":
            collection.add_argument("--interval", type=int, default=300, help="Пауза между циклами, секунды")
        else:
            collection.add_argument("--retry-now", action="store_true",
                                    help="Повторить ошибочные запросы после исправления доступа/настроек")
            collection.add_argument("--verbose", action="store_true")
    status = commands.add_parser("status", help="Показать состояние автоматического сбора")
    status.add_argument("--db", type=Path, default=DEFAULT_DB)
    export = commands.add_parser("export-corpus", help="Экспортировать собранные статьи для ручной разметки")
    export.add_argument("--db", type=Path, default=DEFAULT_DB)
    export.add_argument("--output", type=Path, help="Новый JSONL-файл; по умолчанию stdout")
    publish = commands.add_parser("build-site", help="Собрать статический сайт с подборкой реальных результатов")
    publish.add_argument("--db", type=Path, default=DEFAULT_DB)
    publish.add_argument("--output", type=Path, default=Path("_site"))
    publish.add_argument("--limit", type=int, default=30)
    reextract = commands.add_parser("reextract", help="Повторно извлечь текст из сохранённых HTML без загрузки сайтов")
    reextract.add_argument("--db", type=Path, default=DEFAULT_DB)
    reextract.add_argument("--source", action="append", choices=["rt", "tass", "ria"])
    reanalyze = commands.add_parser("reanalyze", help="Пересчитать сохранённые тексты новой версией правил без загрузки сайтов")
    reanalyze.add_argument("--db", type=Path, default=DEFAULT_DB)
    reanalyze.add_argument("--source", action="append", choices=["rt", "tass", "ria"])
    args = parser.parse_args()
    try:
        if args.command == "serve":
            serve(args.host, args.port, args.db)
            return 0
        if args.command == "analyze":
            text = args.file.read_text(encoding="utf-8") if args.file else sys.stdin.read()
            result = analyze({"title": args.title, "text": text, "source": args.source})
        elif args.command == "evaluate":
            with args.file.open(encoding="utf-8") as corpus:
                result = evaluate(json.loads(line) for line in corpus if line.strip())
        elif args.command in {"collect", "watch"}:
            overrides = {}
            for item in args.feed or []:
                key, separator, value = item.partition("=")
                if not separator or not value or key in overrides:
                    raise ValueError("Используйте уникальные параметры --feed ID=HTTPS_URL.")
                overrides[key] = value
            sources = selected_sources(args.source, overrides)
            if args.command == "watch":
                watch(args.db, sources, args.interval, args.limit, args.revisit_seconds)
                return 0
            with collection_lock(args.db), Store(args.db) as store:
                if args.retry_now:
                    store.retry_now([source.id for source in sources], utcnow())
                logger = (lambda event: print(json.dumps(event, ensure_ascii=False), flush=True)) if args.verbose else None
                result = collect_once(store, sources, args.limit, args.revisit_seconds, log=logger)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["success"] else 1
        elif args.command == "status":
            with Store(args.db) as store:
                result = store.status()
        elif args.command == "build-site":
            with Store(args.db) as store:
                result = build_site(store, args.output, args.limit)
        elif args.command in {"reextract", "reanalyze"}:
            with collection_lock(args.db), Store(args.db) as store:
                result = (reextract_current if args.command == "reextract" else reanalyze_current)(store, args.source)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result["success"] else 1
        else:
            with Store(args.db) as store:
                if args.output:
                    args.output.parent.mkdir(parents=True, exist_ok=True)
                    with args.output.open("x", encoding="utf-8") as output:
                        for row in store.export_corpus():
                            output.write(json.dumps(row, ensure_ascii=False) + "\n")
                else:
                    for row in store.export_corpus():
                        print(json.dumps(row, ensure_ascii=False))
            return 0
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f"Ошибка: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

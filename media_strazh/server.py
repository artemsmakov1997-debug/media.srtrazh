"""Local development API and a manual article-analysis form."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlsplit

from .analysis import MAX_CHARS, VERSION, analyze, taxonomy
from .sources import SOURCES
from .storage import DEFAULT_DB, Store

MAX_REQUEST_BYTES = MAX_CHARS * 6 + 4096


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/health":
            self._send(200, {"status": "ok", "algorithm_version": VERSION})
        elif path == "/api/v1/taxonomy":
            self._send(200, {"categories": taxonomy()})
        elif path == "/":
            self._send(200, Path(__file__).with_name("web").joinpath("index.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif path == "/articles":
            self._send(200, Path(__file__).with_name("web").joinpath("articles.html").read_bytes(),
                       "text/html; charset=utf-8")
        elif path in {"/api/v1/articles", "/api/v1/collection/status"} or path.startswith("/api/v1/articles/"):
            self._collection_get(path)
        else:
            self._send(404, {"error": "Маршрут не найден."})

    def _collection_get(self, path):
        database = getattr(self.server, "db_path", None)
        if database is None or not Path(database).is_file():
            self._send(503, {"error": "База сбора не подключена к серверу."})
            return
        try:
            with Store(database) as store:
                if path == "/api/v1/collection/status":
                    self._send(200, store.status())
                elif path == "/api/v1/articles":
                    query = parse_qs(urlsplit(self.path).query)
                    source = query.get("source", [None])[0]
                    limit = int(query.get("limit", ["25"])[0])
                    offset = int(query.get("offset", ["0"])[0])
                    if (source is not None and source not in SOURCES) or not 1 <= limit <= 100 or offset < 0:
                        raise ValueError("Недопустимые параметры списка статей.")
                    self._send(200, {"items": store.articles(source, limit, offset), "limit": limit, "offset": offset})
                else:
                    article_id = int(path.rsplit("/", 1)[-1])
                    item = store.article(article_id)
                    self._send(200, item) if item else self._send(404, {"error": "Собранная статья не найдена."})
        except ValueError:
            self._send(400, {"error": "Проверьте источник, идентификатор, limit (1–100) и offset (от 0)."})
        except sqlite3.Error:
            self._send(503, {"error": "Не удалось прочитать базу сбора."})

    def do_POST(self):
        if self.path != "/api/v1/analyze":
            self._send(404, {"error": "Маршрут не найден."})
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self._send(415, {"error": "Используйте Content-Type: application/json."})
            return
        try:
            if self.headers.get("Transfer-Encoding"):
                raise ValueError("Передавайте JSON с заголовком Content-Length.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= MAX_REQUEST_BYTES:
                self.close_connection = True
                self._send(413, {"error": "Недопустимый размер запроса."})
                return
            document = json.loads(self.rfile.read(length))
            result = analyze(document)
        except (ValueError, UnicodeError):
            self._send(400, {"error": "Некорректный JSON или документ. Нужен непустой text, строковые поля и не более 200000 символов."})
            return
        except TimeoutError:
            self.close_connection = True
            self._send(408, {"error": "Время передачи запроса истекло."})
            return
        self._send(200, result)


def serve(host="127.0.0.1", port=8001, database=DEFAULT_DB):
    with Store(database):
        pass
    server = ThreadingHTTPServer((host, port), Handler)
    server.db_path = Path(database).resolve()
    print(f"МЕДИА.СТРАЖ: локальный анализатор на {host}:{server.server_port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

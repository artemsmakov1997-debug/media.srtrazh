"""Serve an isolated, same-origin design comparison without changing production files."""
import argparse
import json
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from media_strazh.browser import DEFAULT_RUNTIME, engine_bundle, prepare_runtime, runtime_assets


def make_handler(snapshot, runtime):
    class PreviewHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(ROOT), **kwargs)

        def log_message(self, *args):
            pass

        def do_GET(self):
            path = unquote(urlsplit(self.path).path)
            if path == '/':
                self.send_response(302)
                self.send_header('Location', '/design-preview/analysis/compare.html')
                self.end_headers()
                return
            if path == '/data/analysis.json':
                return self.payload(snapshot.read_bytes(), 'application/json; charset=utf-8')
            if path == '/data/manual-engine.json':
                return self.payload(json.dumps(engine_bundle(), ensure_ascii=False).encode(), 'application/json; charset=utf-8')
            if path.startswith('/vendor/pyodide/'):
                file = runtime / Path(path).name
                allowed = {'pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'pyodide-lock.json', 'python_stdlib.zip'}
                if file.name in allowed and file.is_file():
                    return self.payload(file.read_bytes(), 'application/wasm' if file.suffix == '.wasm' else self.guess_type(str(file)))
                return self.send_error(404)
            file = (ROOT / path.lstrip('/')).resolve()
            public_suffixes = {'.html', '.css', '.js', '.png', '.svg', '.ico', '.ttf', '.woff2', '.txt'}
            if (not file.is_relative_to(ROOT) or any(part.startswith('.') for part in file.relative_to(ROOT).parts)
                    or file.suffix.lower() not in public_suffixes or not file.is_file()):
                return self.send_error(404)
            return super().do_GET()

        def payload(self, body, content_type):
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)
    return PreviewHandler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--bind', default='127.0.0.1')
    parser.add_argument('--runtime', type=Path, default=DEFAULT_RUNTIME)
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'design-preview/analysis/snapshot.json')
    options = parser.parse_args()
    if not options.snapshot.is_file():
        parser.error('Не найдена закреплённая публичная подборка для сравнения.')
    try:
        runtime_assets(options.runtime)
    except (OSError, ValueError):
        print('Подготавливаем закреплённый браузерный движок с проверкой SHA-512…', flush=True)
        prepare_runtime(options.runtime)
    server = ThreadingHTTPServer((options.bind, options.port), make_handler(options.snapshot, options.runtime))
    print(f'Предпросмотр: http://{options.bind}:{server.server_port}/', flush=True)
    print('До / После используют одну закреплённую подборку. Для остановки: Ctrl+C.', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()

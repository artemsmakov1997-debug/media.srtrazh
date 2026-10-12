"""Verified HTTPS, publisher-scoped redirects, robots.txt and request pacing."""

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import gzip
import io
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlsplit, urlunsplit

from .sources import Source, normalize_url

BOT_NAME = "MediaStrazhBot"
USER_AGENT = "MediaStrazhBot/0.2 (+https://github.com/artemsmakov1997-debug/media.srtrazh)"
MAX_DOWNLOAD = 8 * 1024 * 1024


def _request_url(url, source):
    """Robots has a host scope; all content URLs keep the stricter channel scope."""
    parsed = urlsplit(url)
    if parsed.path == "/robots.txt":
        try:
            valid_port = parsed.port in (None, 443)
        except ValueError:
            valid_port = False
        if (parsed.scheme != "https" or parsed.hostname not in source.hosts or
                parsed.username is not None or parsed.password is not None or
                not valid_port or parsed.query or parsed.fragment):
            raise ValueError("Недопустимый адрес robots.txt.")
        return urlunsplit(("https", parsed.hostname, "/robots.txt", "", ""))
    normalized = normalize_url(url, source)
    # Telegram's /s view contains the text, whereas its landing page need not.
    if source.platform == "telegram" and parsed.path.startswith("/s/") and re.fullmatch(r"/[^/]+/[1-9][0-9]*", urlsplit(normalized).path):
        value = urlsplit(normalized)
        return urlunsplit((value.scheme, value.netloc, "/s" + value.path, value.query, ""))
    return normalized


class FetchError(RuntimeError):
    def __init__(self, message, retry_after=0, status_code=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.status_code = status_code


class PublisherRedirects(HTTPRedirectHandler):
    def __init__(self, source, authorize=None):
        self.source = source
        self.authorize = authorize

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            normalized = _request_url(newurl, self.source)
            if urlsplit(newurl).path == "/robots.txt" and urlsplit(req.full_url).path != "/robots.txt":
                raise ValueError("Публикация не должна перенаправляться в robots.txt.")
        except ValueError as exc:
            raise FetchError("Перенаправление выходит за разрешённый домен источника.") from exc
        if self.authorize is not None:
            self.authorize(req.full_url, normalized)
        return super().redirect_request(req, fp, code, msg, headers, normalized)


@dataclass(frozen=True)
class Response:
    url: str
    data: bytes
    content_type: str
    charset: str | None = None

    def text(self):
        encoding = self.charset
        if not encoding:
            meta = re.search(br"charset\s*=\s*[\"']?([a-zA-Z0-9_-]+)", self.data[:10000], re.I)
            encoding = meta.group(1).decode("ascii") if meta else "utf-8"
        try:
            return self.data.decode(encoding)
        except (UnicodeError, LookupError) as exc:
            raise FetchError("Не удалось декодировать текст в заявленной кодировке.") from exc


def _retry_after(value):
    if not value:
        return 0
    try:
        return max(0, int(value))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            return max(0, int((date - datetime.now(timezone.utc)).total_seconds()))
        except (ValueError, TypeError, OverflowError):
            return 0


class SourceClient:
    def __init__(self, source: Source, timeout=12, minimum_delay=2, stop_event=None, request_state=None, deadline=None):
        self.source = source
        self.timeout = timeout
        self.minimum_delay = minimum_delay
        self.opener = build_opener(PublisherRedirects(source, self._authorize_redirect))
        self.robots = None
        self.robots_error = None
        self.last_request = None
        self.stop_event = stop_event
        self.request_state = request_state if request_state is not None else {"last_requests": {}, "robots": {}, "robots_errors": {}}
        self.deadline = deadline

    def _check_deadline(self):
        if self.stop_event is not None and self.stop_event.is_set():
            raise FetchError("Сбор остановлен.")
        if self.deadline is not None and time.monotonic() >= self.deadline:
            raise FetchError("Истёк бюджет времени этого цикла сбора; источник будет проверен в следующем запуске.", retry_after=300)

    def _pace(self, url):
        self._check_deadline()
        host = urlsplit(url).hostname
        if self.stop_event is not None and self.stop_event.is_set():
            raise FetchError("Сбор остановлен.")
        delay = self.minimum_delay
        robots = self.request_state["robots"].get(host)
        if robots is not None:
            delay = max(delay, robots.crawl_delay(BOT_NAME) or 0)
            rate = robots.request_rate(BOT_NAME)
            if rate and rate.requests > 0:
                # Conservative spacing ensures no burst exceeds Request-rate.
                delay = max(delay, rate.seconds / rate.requests)
        last_request = self.request_state["last_requests"].get(host)
        if last_request is not None:
            remaining = delay - (time.monotonic() - last_request)
            if self.deadline is not None and remaining >= self.deadline - time.monotonic():
                raise FetchError("Задержка robots.txt превышает оставшийся бюджет цикла; запрос отложен.", retry_after=300)
            while remaining > 0:
                if self.stop_event is None:
                    time.sleep(min(remaining, 30))
                elif self.stop_event.wait(min(remaining, 30)):
                    raise FetchError("Сбор остановлен.")
                remaining = delay - (time.monotonic() - last_request)
                self._check_deadline()
        self.last_request = time.monotonic()
        self.request_state["last_requests"][host] = self.last_request

    def _authorize_redirect(self, previous, target):
        if urlsplit(previous).path == "/robots.txt":
            if (urlsplit(target).hostname != urlsplit(previous).hostname or
                    urlsplit(target).path != "/robots.txt"):
                raise FetchError("Перенаправление robots.txt должно сохранять его домен и путь.")
        else:
            robots = self.prepare(target)
            if not robots.can_fetch(BOT_NAME, target):
                raise FetchError("robots.txt запрещает путь перенаправления для сборщика.", retry_after=3600)
        self._pace(target)

    def _get(self, url):
        url = _request_url(url, self.source)
        self._pace(url)
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        try:
            timeout = self.timeout if self.deadline is None else max(0.05, min(self.timeout, self.deadline - time.monotonic()))
            with self.opener.open(request, timeout=timeout) as response:
                chunks, size = [], 0
                read = getattr(response, "read1", response.read)
                while True:
                    self._check_deadline()
                    chunk = read(min(65536, MAX_DOWNLOAD + 1 - size))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > MAX_DOWNLOAD:
                        raise FetchError("Ответ превышает лимит загрузки 8 МиБ.")
                data = b"".join(chunks)
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                        data = compressed.read(MAX_DOWNLOAD + 1)
                    if len(data) > MAX_DOWNLOAD:
                        raise FetchError("Распакованный ответ превышает лимит 8 МиБ.")
                elif response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
                    raise FetchError("Неподдерживаемое сжатие ответа сервера.")
                self._check_deadline()
                final_url = _request_url(response.url, self.source)
                return Response(final_url if urlsplit(final_url).path == "/robots.txt" else normalize_url(final_url, self.source), data,
                                response.headers.get_content_type(), response.headers.get_content_charset())
        except HTTPError:
            raise
        except (URLError, OSError, EOFError) as exc:
            raise FetchError(f"Ошибка HTTPS-загрузки {self.source.host}: {exc}") from exc

    def prepare(self, url=None):
        host = urlsplit(normalize_url(url, self.source)).hostname if url is not None else self.source.host
        if host in self.request_state["robots"]:
            self.robots = self.request_state["robots"][host]
            return self.robots
        if host in self.request_state["robots_errors"]:
            raise self.request_state["robots_errors"][host]
        parser = RobotFileParser(f"https://{host}/robots.txt")
        try:
            response = self._get(parser.url)
            if (urlsplit(response.url).hostname != host or urlsplit(response.url).path != "/robots.txt" or
                    response.content_type in {"text/html", "application/xhtml+xml"}):
                raise FetchError("Вместо robots.txt получена HTML-страница или другой адрес; доступ к публикациям не подтверждён.", retry_after=3600)
            parser.parse(response.data.decode("utf-8", errors="replace").splitlines())
        except HTTPError as exc:
            if exc.code == 404:
                parser.allow_all = True
            else:
                error = FetchError(f"Не удалось проверить robots.txt: HTTP {exc.code}.",
                                   max(3600, _retry_after(exc.headers.get("Retry-After"))), exc.code)
                if host == self.source.host:
                    self.robots_error = error
                self.request_state["robots_errors"][host] = error
                raise error from exc
        except FetchError as exc:
            if host == self.source.host:
                self.robots_error = exc
            self.request_state["robots_errors"][host] = exc
            raise
        self.robots = parser
        self.request_state["robots"][host] = parser
        return parser

    def get_feed(self):
        """Read the public RSS endpoint even when robots.txt itself returns 403.

        This permits link discovery only. Article requests still require a robots
        check and are never fetched after that check fails.
        """
        try:
            self.prepare(self.source.feed_url)
        except FetchError as exc:
            if exc.status_code != 403 or self.source.platform == "telegram":
                raise
            try:
                return self._get(self.source.feed_url)
            except HTTPError as error:
                raise FetchError(f"RSS отклонена источником: HTTP {error.code}.",
                                 _retry_after(error.headers.get("Retry-After")), error.code) from error
        try:
            return self.get(self.source.feed_url)
        except FetchError as exc:
            if exc.status_code == 404 and self.source.platform == "website":
                return self.discover_feed()
            raise

    def discover_feed(self):
        """One bounded alternate-link attempt from the publisher's own homepage."""
        if self.source.platform != "website":
            raise FetchError("RSS-autodiscovery неприменима к Telegram.")
        from .extraction import HTMLTree
        homepage = self.homepage()
        if homepage.content_type not in {"text/html", "application/xhtml+xml"}:
            raise FetchError("Главная страница издателя не является HTML для поиска официальной RSS.")
        tree = HTMLTree()
        tree.feed(homepage.text())
        tree.close()
        for node in tree.nodes:
            if (node.tag != "link" or "alternate" not in (node.attrs.get("rel") or "").lower().split() or
                    (node.attrs.get("type") or "").lower() not in {"application/rss+xml", "application/atom+xml"}):
                continue
            try:
                endpoint = normalize_url(urljoin(homepage.url, node.attrs.get("href", "")), self.source)
            except ValueError:
                continue
            if endpoint != self.source.feed_url:
                return self.get(endpoint)
        raise FetchError("На главной странице не найдена официальная RSS/Atom-ссылка в разрешённых доменах.")

    def homepage(self):
        self._check_deadline()
        url = self.source.homepage_url or f"https://{self.source.host}/"
        cached = self.request_state.setdefault("homepages", {})
        if url not in cached:
            cached[url] = self.get(url)
        return cached[url]

    def get(self, url):
        url = normalize_url(url, self.source)
        if self.source.platform == "telegram" and re.fullmatch(r"/[^/]+/[1-9][0-9]*", urlsplit(url).path):
            value = urlsplit(url)
            url = urlunsplit(("https", value.netloc, "/s" + value.path, "", ""))
        robots = self.prepare(url)
        if not robots.can_fetch(BOT_NAME, url):
            raise FetchError("robots.txt запрещает загрузку этого пути для сборщика.", retry_after=3600)
        try:
            return self._get(url)
        except HTTPError as exc:
            raise FetchError(f"Загрузка отклонена источником: HTTP {exc.code}.",
                             _retry_after(exc.headers.get("Retry-After")), exc.code) from exc

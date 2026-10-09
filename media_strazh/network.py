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

from .sources import Source, normalize_url

BOT_NAME = "MediaStrazhBot"
USER_AGENT = "MediaStrazhBot/0.2 (+https://github.com/artemsmakov1997-debug/media.srtrazh)"
MAX_DOWNLOAD = 8 * 1024 * 1024


class FetchError(RuntimeError):
    def __init__(self, message, retry_after=0, status_code=None):
        super().__init__(message)
        self.retry_after = retry_after
        self.status_code = status_code


class PublisherRedirects(HTTPRedirectHandler):
    def __init__(self, source):
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        try:
            normalized = normalize_url(newurl, self.source)
        except ValueError as exc:
            raise FetchError("Перенаправление выходит за разрешённый домен источника.") from exc
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
    def __init__(self, source: Source, timeout=20, minimum_delay=2, stop_event=None):
        self.source = source
        self.timeout = timeout
        self.minimum_delay = minimum_delay
        self.opener = build_opener(PublisherRedirects(source))
        self.robots = None
        self.robots_error = None
        self.last_request = None
        self.stop_event = stop_event

    def _get(self, url):
        url = normalize_url(url, self.source)
        if self.stop_event is not None and self.stop_event.is_set():
            raise FetchError("Сбор остановлен.")
        delay = self.minimum_delay
        if self.robots is not None:
            delay = max(delay, self.robots.crawl_delay(BOT_NAME) or 0)
            rate = self.robots.request_rate(BOT_NAME)
            if rate and rate.requests > 0:
                # Conservative spacing ensures no burst exceeds Request-rate.
                delay = max(delay, rate.seconds / rate.requests)
        if self.last_request is not None:
            remaining = delay - (time.monotonic() - self.last_request)
            while remaining > 0:
                if self.stop_event is None:
                    time.sleep(min(remaining, 30))
                elif self.stop_event.wait(min(remaining, 30)):
                    raise FetchError("Сбор остановлен.")
                remaining = delay - (time.monotonic() - self.last_request)
        self.last_request = time.monotonic()
        request = Request(url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                data = response.read(MAX_DOWNLOAD + 1)
                if len(data) > MAX_DOWNLOAD:
                    raise FetchError("Ответ превышает лимит загрузки 8 МиБ.")
                if response.headers.get("Content-Encoding", "").lower() == "gzip":
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
                        data = compressed.read(MAX_DOWNLOAD + 1)
                    if len(data) > MAX_DOWNLOAD:
                        raise FetchError("Распакованный ответ превышает лимит 8 МиБ.")
                elif response.headers.get("Content-Encoding", "identity").lower() not in ("identity", ""):
                    raise FetchError("Неподдерживаемое сжатие ответа сервера.")
                return Response(normalize_url(response.url, self.source), data,
                                response.headers.get_content_type(), response.headers.get_content_charset())
        except HTTPError:
            raise
        except (URLError, OSError, EOFError) as exc:
            raise FetchError(f"Ошибка HTTPS-загрузки {self.source.host}: {exc}") from exc

    def prepare(self):
        if self.robots is not None:
            return
        if self.robots_error is not None:
            raise self.robots_error
        parser = RobotFileParser(f"https://{self.source.host}/robots.txt")
        try:
            response = self._get(parser.url)
            parser.parse(response.data.decode("utf-8", errors="replace").splitlines())
        except HTTPError as exc:
            if exc.code == 404:
                parser.allow_all = True
            else:
                error = FetchError(f"Не удалось проверить robots.txt: HTTP {exc.code}.",
                                   max(3600, _retry_after(exc.headers.get("Retry-After"))), exc.code)
                self.robots_error = error
                raise error from exc
        self.robots = parser

    def get_feed(self):
        """Read the public RSS endpoint even when robots.txt itself returns 403.

        This permits link discovery only. Article requests still require a robots
        check and are never fetched after that check fails.
        """
        try:
            self.prepare()
        except FetchError as exc:
            if exc.status_code != 403:
                raise
            try:
                return self._get(self.source.feed_url)
            except HTTPError as error:
                raise FetchError(f"RSS отклонена источником: HTTP {error.code}.",
                                 _retry_after(error.headers.get("Retry-After")), error.code) from error
        return self.get(self.source.feed_url)

    def get(self, url):
        url = normalize_url(url, self.source)
        if self.robots is None:
            self.prepare()
        if not self.robots.can_fetch(BOT_NAME, url):
            raise FetchError("robots.txt запрещает загрузку этого пути для сборщика.", retry_after=3600)
        try:
            return self._get(url)
        except HTTPError as exc:
            raise FetchError(f"Загрузка отклонена источником: HTTP {exc.code}.",
                             _retry_after(exc.headers.get("Retry-After"))) from exc

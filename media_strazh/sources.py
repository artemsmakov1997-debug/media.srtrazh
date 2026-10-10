"""Publisher adapters for the three sources selected by the project owner."""

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    host: str
    feed_url: str
    body_classes: tuple[str, ...]
    lead_classes: tuple[str, ...] = ()


SOURCES = {
    "rt": Source("rt", "RT на русском", "russian.rt.com", "https://russian.rt.com/rss",
                 ("article__text", "article__body"), ("article__summary",)),
    "tass": Source("tass", "ТАСС", "tass.ru", "https://tass.ru/rss/v2.xml",
                   ("news-content__text", "news-content__content", "text-block",
                    "text-content", "article__text", "article-body", "NewsContent_content",
                    "ContentBlock_content")),
    "ria": Source("ria", "РИА Новости", "ria.ru", "https://ria.ru/export/rss2/archive/index.xml",
                  ("article__text",)),
}


def normalize_url(url: str, source: Source) -> str:
    """Accept only publisher HTTPS destinations; remove known tracking fields."""
    parsed = urlsplit(url)
    if (parsed.scheme not in ("http", "https") or parsed.hostname != source.host or
            parsed.username is not None or parsed.password is not None or parsed.port not in (None, 443)):
        raise ValueError(f"URL должен вести на https://{source.host} без учётных данных и сторонних портов.")
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"yclid", "gclid", "fbclid"}]
    return urlunsplit(("https", source.host, parsed.path or "/", urlencode(sorted(query)), ""))

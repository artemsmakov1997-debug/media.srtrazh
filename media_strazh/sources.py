"""Explicit publisher/platform registry; hosts and Telegram channels are scoped."""

from dataclasses import dataclass, replace
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    host: str
    feed_url: str
    body_classes: tuple[str, ...]
    lead_classes: tuple[str, ...] = ()
    allowed_hosts: tuple[str, ...] = ()
    publisher_id: str = ""
    platform: str = "website"
    channel: str = ""
    configuration_error: str = ""
    body_attributes: tuple[tuple[str, str], ...] = ()
    homepage_url: str = ""

    @property
    def publisher(self):
        return self.publisher_id or self.id

    @property
    def hosts(self):
        return tuple(dict.fromkeys((self.host, *self.allowed_hosts)))


SOURCES = {
    "rt": Source("rt", "RT на русском", "russian.rt.com", "https://russian.rt.com/rss",
                 ("article__text", "article__body"), ("article__summary",)),
    "tass": Source("tass", "ТАСС", "tass.ru", "https://tass.ru/rss/v2.xml",
                   ("news-content__text", "news-content__content", "text-block",
                    "text-content", "article__text", "article-body", "NewsContent_content",
                    "ContentBlock_content")),
    "ria": Source("ria", "РИА Новости", "ria.ru", "https://ria.ru/export/rss2/archive/index.xml",
                  ("article__text",)),
    "interfax": Source("interfax", "Интерфакс", "www.interfax.ru", "https://www.interfax.ru/rss.asp",
                       ("text", "text-m"), allowed_hosts=("interfax.ru",)),
    "kommersant": Source("kommersant", "Коммерсантъ", "www.kommersant.ru", "https://www.kommersant.ru/RSS/news.xml",
                         ("article_text_wrapper", "article__text"), allowed_hosts=("kommersant.ru",)),
    "vedomosti": Source("vedomosti", "Ведомости", "www.vedomosti.ru", "https://www.vedomosti.ru/rss/news",
                        ("article__body", "article-content"), allowed_hosts=("vedomosti.ru",)),
    "rbc": Source("rbc", "РБК", "www.rbc.ru", "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
                  ("article__text", "article__text__overview"), allowed_hosts=("rbc.ru", "rssexport.rbc.ru")),
    "izvestia": Source("izvestia", "Известия", "iz.ru", "https://iz.ru/xml/rss/all.xml",
                       ("text-article", "article__text", "field-name-body")),
    "rg": Source("rg", "Российская газета", "rg.ru", "https://rg.ru/xml/index.xml",
                 ("b-material-wrapper__text", "PageArticleContent_text", "article__text")),
    "lenta": Source("lenta", "Лента.ру", "lenta.ru", "https://lenta.ru/rss/news",
                    ("topic-body__content", "topic-body__content-text")),
    "meduza": Source("meduza", "Медуза", "meduza.io", "https://meduza.io/rss/all",
                     ("GeneralMaterial-module-article", "GeneralMaterial-article", "RichText-root")),
    "novayagazeta": Source("novayagazeta", "Новая газета Европа", "novayagazeta.eu", "https://novayagazeta.eu/rss",
                           ("article-body", "article__body", "article__text"), allowed_hosts=("www.novayagazeta.eu",),
                           body_attributes=(("data-body", "true"),)),
    "fontanka": Source("fontanka", "Фонтанка.ру", "www.fontanka.ru", "https://www.fontanka.ru/fontanka.rss",
                       ("article-body", "article__text", "text-block"), allowed_hosts=("fontanka.ru",)),
    "currenttime": Source("currenttime", "Настоящее Время", "www.currenttime.tv", "https://www.currenttime.tv/api/zrqiteuuir",
                          ("wsw",), allowed_hosts=("currenttime.tv",)),
    "dw": Source("dw", "Deutsche Welle", "www.dw.com", "https://rss.dw.com/rdf/rss-ru-all",
                 ("rich-text", "longText", "article__text"), allowed_hosts=("dw.com", "rss.dw.com"),
                 homepage_url="https://www.dw.com/ru/"),
    "bbc": Source("bbc", "BBC News Русская служба", "www.bbc.com", "https://feeds.bbci.co.uk/russian/rss.xml",
                  (), allowed_hosts=("bbc.com", "www.bbc.co.uk", "bbc.co.uk", "feeds.bbci.co.uk"),
                  body_attributes=(("data-component", "text-block"),), homepage_url="https://www.bbc.com/russian"),
}

# First-party-confirmed channels; evidence is recorded in docs/sources.md.
OFFICIAL_CHANNELS = {"rt": "rt_russian", "ria": "rian_ru", "interfax": "interfaxonline",
                     "meduza": "meduzalive", "novayagazeta": "novaya_europe",
                     "currenttime": "currenttime", "dw": "dwglavnoe", "bbc": "bbcrussian"}
# Explicitly selected by the user; keep ownership evidence separate from selection.
USER_CHANNELS = {"tass": "tass_agency", "kommersant": "kommersant", "vedomosti": "vedomosti",
                 "rbc": "rbc_news", "izvestia": "izvestia", "rg": "rgrunews", "fontanka": "fontankaspb"}
for _publisher, _website in list(SOURCES.items()):
    _channel = OFFICIAL_CHANNELS.get(_publisher) or USER_CHANNELS.get(_publisher, "")
    SOURCES[_publisher + "_telegram"] = Source(
        _publisher + "_telegram", _website.name + " · Telegram", "t.me",
        "https://t.me/s/" + _channel if _channel else "", (),
        publisher_id=_publisher, platform="telegram", channel=_channel,
        configuration_error="Не подтверждён адрес официального Telegram-канала издателя." if not _channel else "")

# oldlentach identifies Лентач, not the newsroom of Лента.ру. It is a separate
# user-selected publisher; never include its posts in Лента.ру's group or scores.
SOURCES["oldlentach_telegram"] = Source(
    "oldlentach_telegram", "Лентач · Telegram", "t.me", "https://t.me/s/oldlentach", (),
    publisher_id="oldlentach", platform="telegram", channel="oldlentach")

PUBLISHERS = tuple(key for key, source in SOURCES.items() if source.platform == "website")


def resolve_source(source, stored_feed_url):
    """Restore a channel verified by collection, retaining its publisher group."""
    if source.platform != "telegram" or source.channel or not isinstance(stored_feed_url, str):
        return source
    if not re.fullmatch(r"https://t\.me/s/[A-Za-z][A-Za-z0-9_]{4,31}", stored_feed_url):
        return source
    channel = stored_feed_url.rsplit("/", 1)[-1]
    return replace(source, channel=channel, feed_url=stored_feed_url, configuration_error="")


def channel_from_homepage(html, website):
    """Trust one unambiguous Telegram address in first-party social navigation."""
    from .extraction import HTMLTree
    tree = HTMLTree()
    tree.feed(html)
    tree.close()
    candidates = {}
    for node in tree.nodes:
        if node.tag != "a":
            continue
        try:
            parsed = urlsplit(node.attrs.get("href", ""))
            port = parsed.port
        except ValueError:
            continue
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in {"t.me", "telegram.me", "tgclick.com"}:
            continue
        if parsed.username is not None or parsed.password is not None or port not in (None, 443) or parsed.query or parsed.fragment:
            continue
        match = re.fullmatch(r"/(?:s/)?([A-Za-z][A-Za-z0-9_]{4,31})/?", parsed.path)
        if not match:
            continue
        if match[1].casefold().endswith("bot"):
            # Feedback/submission bots in the same footer are not news channels.
            continue
        ancestor, social, excluded = node, False, False
        while ancestor is not None:
            attrs = " ".join((ancestor.attrs.get("class") or "", ancestor.attrs.get("id") or ""))
            if ancestor.tag == "article" or re.search(r"(?:article|topic)[_-](?:body|text|content)", attrs, re.I):
                excluded = True
            if ancestor.tag in {"footer", "header"} or ancestor.attrs.get("role") == "contentinfo" or re.search(r"footer|social", attrs, re.I):
                social = True
            ancestor = ancestor.parent
        if social and not excluded:
            candidates[match[1].casefold()] = match[1]
    if len(candidates) != 1:
        raise ValueError("На официальной странице не найден единственный подтверждаемый Telegram-канал в шапке/подвале; требуется уточнение адреса." if not candidates else
                         "На официальной странице несколько Telegram-каналов: требуется уточнить основной русскоязычный канал.")
    channel = next(iter(candidates.values()))
    return resolve_source(SOURCES[website.id + "_telegram"], "https://t.me/s/" + channel)


def normalize_url(url: str, source: Source) -> str:
    """Accept only publisher HTTPS destinations; remove known tracking fields."""
    parsed = urlsplit(url)
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Некорректный порт URL.") from exc
    if (parsed.scheme not in ("http", "https") or parsed.hostname not in source.hosts or
            parsed.username is not None or parsed.password is not None or port not in (None, 443)):
        raise ValueError(f"URL должен вести на https://{source.host} без учётных данных и сторонних портов.")
    if source.platform == "telegram":
        if not source.channel or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", source.channel):
            raise ValueError("Не настроен подтверждённый публичный Telegram-канал.")
        match = re.fullmatch(r"/(s/)?([A-Za-z][A-Za-z0-9_]{4,31})(?:/([1-9][0-9]*))?/?", parsed.path)
        if not match or match[2].casefold() != source.channel.casefold():
            raise ValueError("URL должен вести на публикацию настроенного Telegram-канала.")
        if match[3]:
            if parsed.query:
                raise ValueError("Telegram-ссылки публикаций должны быть без параметров запроса.")
            path, query = f"/{source.channel}/{match[3]}", ""
        else:
            params = parse_qsl(parsed.query, keep_blank_values=True)
            if params and (len(params) != 1 or params[0][0] != "before" or not re.fullmatch(r"[1-9][0-9]*", params[0][1])):
                raise ValueError("Недопустимые параметры публичной ленты Telegram.")
            path = f"/s/{source.channel}" if match[1] else f"/{source.channel}"
            query = urlencode(params)
        return urlunsplit(("https", source.host, path, query, ""))
    query = [(key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith("utm_") and key.lower() not in {"yclid", "gclid", "fbclid"}]
    path = quote(parsed.path or "/", safe="/:@!$&'()*+,;=-._~%")
    return urlunsplit(("https", parsed.hostname, path, urlencode(sorted(query)), ""))

"""RSS discovery and conservative main-text extraction, without browser execution."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
import re
from urllib.parse import urljoin
import xml.etree.ElementTree as ET

from .analysis import validate_document
from .sources import Source, normalize_url

EXTRACTOR_VERSION = "html-0.3.0"
MAX_FEED_ITEMS = 2000
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "section", "article", "li", "h1", "h2", "h3", "h4", "blockquote", "br", "ul", "ol"}
SKIP = {"script", "style", "nav", "aside", "noscript", "iframe", "form", "button", "svg"}
NOISE = re.compile(r"(?:^|[\s_-])(?:share|related|recommend|social|banner|advert|read-also|read-more)(?:[\s_-]|$)", re.I)


@dataclass
class Node:
    tag: str
    attrs: dict
    parent: "Node | None" = None
    children: list = field(default_factory=list)


class HTMLTree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("root", {})
        self.stack = [self.root]
        self.nodes = []

    def handle_starttag(self, tag, attrs):
        node = Node(tag, dict(attrs), self.stack[-1])
        self.stack[-1].children.append(node)
        self.nodes.append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def node_text(node, clean=True):
    # Iterative traversal also handles heavily nested page markup.
    chunks, stack = [], [node]
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            chunks.append(item)
            continue
        if clean and (item.tag in SKIP or NOISE.search(item.attrs.get("class") or "")):
            continue
        block = clean and item.tag in BLOCK
        if block:
            chunks.append("\n")
            stack.append("\n")
        stack.extend(reversed(item.children))
    text = "".join(chunks)
    if not clean:
        return text
    return "\n".join(line.strip() for line in re.sub(r"[ \t\r\xa0]+", " ", text).splitlines() if line.strip())


def plain_text(markup):
    tree = HTMLTree()
    tree.feed(markup)
    tree.close()
    return node_text(tree.root)


def timestamp(value):
    """Normalize aware publisher dates; never guess the timezone of a naive date."""
    if not value or not isinstance(value, str):
        return ""
    try:
        date = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return ""
    if date is None or date.tzinfo is None:
        return ""
    return date.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class FeedEntry:
    url: str
    title: str
    published_at: str = ""


def _local_name(tag):
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(data: bytes, source: Source) -> list[FeedEntry]:
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ValueError("RSS с DTD или объявлениями сущностей не поддерживается.")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("Ответ источника не является корректной RSS/Atom-лентой.") from exc
    if _local_name(root.tag) not in {"rss", "feed", "rdf"}:
        raise ValueError("Получен документ другого типа вместо RSS/Atom.")
    entries, seen = [], set()
    for item in root.iter():
        if _local_name(item.tag) not in {"item", "entry"}:
            continue
        title, link, date = "", "", ""
        for child in item:
            name = _local_name(child.tag)
            value = "".join(child.itertext()).strip()
            if name == "title":
                title = plain_text(value)
            elif name == "link" and child.attrib.get("rel", "alternate") == "alternate":
                link = child.attrib.get("href") or value
            elif name in {"pubdate", "published", "date", "updated"} and not date:
                date = timestamp(value)
        if not link or not title:
            continue
        try:
            url = normalize_url(urljoin(source.feed_url, link), source)
        except ValueError:
            continue
        if url not in seen:
            entries.append(FeedEntry(url, title, date))
            seen.add(url)
        if len(entries) >= MAX_FEED_ITEMS:
            break
    if not entries:
        raise ValueError("Лента не содержит публикаций с допустимыми ссылками и заголовками.")
    return entries


def _structured_articles(data):
    stack = [data]
    while stack:
        current = stack.pop()
        if isinstance(current, list):
            stack.extend(reversed(current))
        elif isinstance(current, dict):
            types = current.get("@type", [])
            if isinstance(types, str):
                types = [types]
            if isinstance(types, list) and any(isinstance(t, str) and t in {"NewsArticle", "Article", "ReportageNewsArticle"} for t in types):
                yield current
            graph = current.get("@graph")
            if isinstance(graph, (dict, list)):
                stack.append(graph)


def extract_article(html: str, url: str, source: Source, entry: FeedEntry) -> dict:
    tree = HTMLTree()
    tree.feed(html)
    tree.close()
    canonical, metadata = normalize_url(url, source), {}
    for node in tree.nodes:
        if node.tag == "meta":
            key = node.attrs.get("property") or node.attrs.get("name")
            if key and node.attrs.get("content"):
                metadata[key.lower()] = node.attrs["content"]
        elif node.tag == "link" and "canonical" in (node.attrs.get("rel") or "").split():
            try:
                canonical = normalize_url(urljoin(url, node.attrs.get("href", "")), source)
            except ValueError:
                pass
    structured = []
    for node in tree.nodes:
        if node.tag != "script" or (node.attrs.get("type") or "").split(";", 1)[0].strip().lower() != "application/ld+json":
            continue
        try:
            structured.extend(_structured_articles(json.loads(node_text(node, clean=False))))
        except (ValueError, RecursionError):
            continue
    matched, unlocated = [], []
    for article in structured:
        body = article.get("articleBody")
        if not isinstance(body, str) or not body.strip():
            continue
        location = article.get("url") or article.get("mainEntityOfPage")
        if isinstance(location, dict):
            location = location.get("@id")
        if isinstance(location, str):
            try:
                if normalize_url(urljoin(url, location), source) in {canonical, normalize_url(url, source)}:
                    matched.append(article)
            except ValueError:
                continue
        elif not location:
            unlocated.append(article)
    chosen = matched[0] if matched else (unlocated[0] if len(unlocated) == 1 else None)
    if chosen:
        body = plain_text(chosen["articleBody"])
        title = plain_text(chosen.get("headline", "")) if isinstance(chosen.get("headline"), str) else ""
        date = timestamp(chosen.get("datePublished"))
        method = "jsonld.articleBody"
    else:
        selected = []
        selected_ids = set()
        for node in tree.nodes:
            classes = (node.attrs.get("class") or "").split()
            matches = any(token == selector or token.startswith(selector + "_")
                          for token in classes for selector in source.body_classes)
            if not matches:
                continue
            parent, nested = node.parent, False
            while parent is not None:
                if id(parent) in selected_ids:
                    nested = True
                    break
                parent = parent.parent
            if not nested:
                selected.append(node)
                selected_ids.add(id(node))
        body = "\n".join(value for node in selected if (value := node_text(node)))
        # RT places the article's opening paragraph outside the main body. RIA's
        # similarly named AI summary is deliberately excluded by its adapter.
        if body and source.lead_classes:
            leads = [node_text(node) for node in tree.nodes
                     if any(token == selector or token.startswith(selector + "_")
                            for token in (node.attrs.get("class") or "").split()
                            for selector in source.lead_classes)]
            leads = list(dict.fromkeys(lead for lead in leads if lead))
            normalized_body = " ".join(body.split())
            additions = [lead for lead in leads if not normalized_body.startswith(" ".join(lead.split()))]
            if additions:
                body = "\n".join([*additions, body])
        title, date, method = "", "", "html.publisher_body"
    # Some opinion pages provide dates/headlines in JSON-LD without articleBody.
    # Use their metadata without replacing the publisher's main text.
    for article in structured:
        location = article.get("url") or article.get("mainEntityOfPage")
        if isinstance(location, dict):
            location = location.get("@id")
        if not isinstance(location, str):
            continue
        try:
            if normalize_url(urljoin(url, location), source) not in {canonical, normalize_url(url, source)}:
                continue
        except ValueError:
            continue
        if not title and isinstance(article.get("headline"), str):
            title = plain_text(article["headline"])
        date = date or timestamp(article.get("datePublished"))
    title = title or metadata.get("og:title", "")
    if not title:
        title = next((node_text(node) for node in tree.nodes if node.tag == "h1"), "")
    title = title or entry.title
    date = date or timestamp(metadata.get("article:published_time")) or entry.published_at
    if len(re.findall(r"[а-яё]", body, re.I)) < 80:
        raise ValueError("Не найден достаточно полный основной текст: RSS-аннотация не используется как замена.")
    document = {"title": title.strip(), "text": body.strip(), "source": source.name,
                "url": canonical, "published_at": date}
    validate_document(document)
    return {"document": document, "extraction_method": method, "extractor_version": EXTRACTOR_VERSION}

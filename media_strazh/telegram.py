"""Public channel preview extraction; no login, private messages or media OCR."""

import re
from urllib.parse import urlsplit, urlunsplit

from .analysis import validate_document
from .extraction import EXTRACTOR_VERSION, MAX_FEED_ITEMS, FeedEntry, HTMLTree, Node, node_text, timestamp
from .sources import normalize_url


def _inside(node, ancestor):
    while node is not None:
        if node is ancestor:
            return True
        node = node.parent
    return False


def preview_posts(html, source):
    """Return only actual message text/captions in this configured channel."""
    tree = HTMLTree()
    tree.feed(html)
    tree.close()
    posts, seen = [], set()
    for container in tree.nodes:
        post = container.attrs.get("data-post", "")
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}/[1-9][0-9]*", post):
            continue
        try:
            url = normalize_url("https://t.me/" + post, source)
        except ValueError:
            continue
        if url in seen:
            continue
        children, stack = [], list(reversed(container.children))
        while stack:
            child = stack.pop()
            if not isinstance(child, Node) or child.attrs.get("data-post"):
                continue
            children.append(child)
            stack.extend(reversed(child.children))
        content = [node for node in children
                   if "tgme_widget_message_text" in (node.attrs.get("class") or "").split()]
        # Telegram renders quoted passages as HTML blockquotes; retain their
        # boundaries so the common analyzer can distinguish cited statements.
        for quoted in children:
            if quoted.tag == "blockquote" and any(_inside(quoted, node) for node in content):
                quoted.children.insert(0, "«")
                quoted.children.append("»")
        # Media-only/deleted posts and unavailable paid content have no text node.
        # Album previews may render the same caption twice for different
        # layouts. Deduplicate complete rendered nodes, not repeated sentences
        # within an author's text: actual rhetorical repetition stays intact.
        body = "\n".join(dict.fromkeys(node_text(node) for node in content)).strip()
        if len(re.findall(r"[а-яё]", body, re.I)) < 3:
            continue
        forwarded = next((node_text(node) for node in children
                          if "tgme_widget_message_forwarded_from" in (node.attrs.get("class") or "").split()), "")
        if forwarded:
            body = forwarded + "\n" + body
        # The first <time> may be a video's duration, not publication time.
        # Bind the date to this message's footer permalink, not an embedded post.
        dates, fallback, has_date_link = set(), set(), False
        for node in children:
            if node.tag != "time":
                continue
            value = timestamp(node.attrs.get("datetime"))
            parent, link = node.parent, None
            while parent is not None and parent is not container:
                if parent.tag == "a" and "tgme_widget_message_date" in (parent.attrs.get("class") or "").split():
                    link = parent
                    break
                parent = parent.parent
            if link is not None:
                has_date_link = True
                try:
                    if value and normalize_url(link.attrs.get("href", ""), source) == url:
                        dates.add(value)
                except ValueError:
                    pass
            elif value and not any(_inside(node, text_node) for text_node in content):
                if "message_video_duration" not in (node.attrs.get("class") or "").split():
                    fallback.add(value)
        date = next(iter(dates)) if len(dates) == 1 else next(iter(fallback)) if not has_date_link and len(fallback) == 1 else ""
        title = " ".join(node_text(content[0]).split())[:250]
        # Count actual message/album photo anchors, not avatars, emoji or link
        # previews. Keep only a bounded observation, never remote image URLs.
        photos = set()
        link_previews = [parent for parent in children
                         if "tgme_widget_message_link_preview" in (parent.attrs.get("class") or "").split()]
        for node in children:
            if (node.tag == "a" and "tgme_widget_message_photo_wrap" in (node.attrs.get("class") or "").split()
                    and not any(_inside(node, parent) for parent in link_previews)):
                try:
                    parsed = urlsplit(node.attrs.get("href", ""))
                    if parsed.query == "single":
                        parsed = parsed._replace(query="")
                    photo = normalize_url(urlunsplit(parsed), source)
                    if re.fullmatch(r"https://t\.me/" + re.escape(source.channel) + r"/[1-9][0-9]*", photo):
                        photos.add(photo)
                except ValueError:
                    pass
        posts.append({"entry": FeedEntry(url, title, date), "text": body, "forwarded": bool(forwarded),
                      "media": {"image_count": min(len(photos), 100)} if photos else None})
        seen.add(url)
        if len(posts) >= MAX_FEED_ITEMS:
            break
    return posts


def parse_preview(html, source):
    posts = preview_posts(html, source)
    if not posts:
        raise ValueError("Публичная Telegram-лента не содержит доступных текстовых публикаций настроенного канала.")
    return [post["entry"] for post in reversed(posts)]


def extract_post(html, url, source, entry):
    canonical = normalize_url(url, source)
    if not re.fullmatch(r"/[^/]+/[1-9][0-9]*", canonical.removeprefix("https://t.me")):
        raise ValueError("Для анализа Telegram нужна ссылка на конкретную публикацию.")
    post = next((post for post in preview_posts(html, source) if post["entry"].url == canonical), None)
    if post is None:
        raise ValueError("Текст запрошенной Telegram-публикации отсутствует в публичном предпросмотре.")
    document = {"title": "", "text": post["text"], "source": source.name,
                "url": canonical, "published_at": post["entry"].published_at or timestamp(entry.published_at)}
    if post["media"]:
        document["media"] = post["media"]
    # Telegram has a single message body, not a separate editorial headline.
    # Do not duplicate its first sentence in title-only rhetorical rules.
    validate_document(document)
    return {"document": document,
            "extraction_method": "telegram.public_message.forwarded" if post["forwarded"] else "telegram.public_message",
            "extractor_version": EXTRACTOR_VERSION}

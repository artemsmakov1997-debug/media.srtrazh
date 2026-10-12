"""BBC Simorgh's public embedded article model; no JavaScript execution."""

from datetime import datetime, timezone
import json
from urllib.parse import urlsplit

from .sources import normalize_url


def _text(block):
    paragraphs, stack = [], [block]
    while stack:
        item = stack.pop()
        if not isinstance(item, dict):
            continue
        model = item.get("model")
        if not isinstance(model, dict):
            continue
        value = model.get("text")
        if item.get("type") == "paragraph" and isinstance(value, str):
            paragraphs.append(value.strip())
        else:
            children = model.get("blocks")
            if isinstance(children, list):
                stack.extend(reversed(children))
    return "\n".join(value for value in paragraphs if value)


def embedded_article(tree, canonical, source):
    from .extraction import node_text
    for node in tree.nodes:
        if (node.tag != "script" or node.attrs.get("id") != "__NEXT_DATA__" or
                node.attrs.get("type") != "application/json"):
            continue
        try:
            payload = json.loads(node_text(node, clean=False))
            if not isinstance(payload, dict) or not isinstance(payload.get("props"), dict):
                continue
            page = payload["props"].get("pageProps")
            if not isinstance(page, dict):
                continue
            if page.get("pageType") != "article" or page.get("service") != "russian" or page.get("status") != 200:
                continue
            data = page.get("pageData")
            if not isinstance(data, dict) or not isinstance(data.get("metadata"), dict):
                continue
            metadata = data["metadata"]
            locators = metadata.get("locators")
            if not isinstance(locators, dict) or not isinstance(locators.get("canonicalUrl"), str):
                continue
            located = normalize_url(locators["canonicalUrl"], source)
            if located != canonical or urlsplit(located).path != page.get("pathname"):
                continue
            content = data.get("content")
            if not isinstance(content, dict) or not isinstance(content.get("model"), dict):
                continue
            blocks = content["model"].get("blocks")
            if not isinstance(blocks, list):
                continue
            body, title = [], ""
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type")
                if kind == "headline":
                    title = _text(block)
                elif kind in {"text", "subheadline", "list", "orderedList", "unorderedList"}:
                    body.append(_text(block))
                elif kind in {"quote", "quotation", "pullquote"}:
                    value = _text(block)
                    if value:
                        body.append("«" + value + "»")
            published = metadata.get("firstPublished")
            date = (datetime.fromtimestamp(published / 1000, timezone.utc).isoformat()
                    if isinstance(published, (int, float)) else "")
            text = "\n".join(value for value in body if value)
            if text:
                return {"text": text, "title": title, "published_at": date}
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            continue
    return None

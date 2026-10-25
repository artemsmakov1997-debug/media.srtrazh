"""Generate clean GitHub Pages URLs without removing the original HTML assets.

GitHub Pages serves `/method/` from `/method/index.html`. Copies use an
absolute base URL so assets, workers, fetches and stylesheet links still resolve
from the domain root. Legacy `.html` pages remain published as redirect-capable
fallbacks for existing bookmarks.
"""
import re
from pathlib import Path

DOMAIN = "https://media-strazh.ru"
CLEAN_ROUTES = ("about", "analysis", "archive", "business", "help", "method")
# Restrict rewriting to exact *quoted* page URLs rather than arbitrary text.
_QUOTED_PAGE = re.compile(
    r"""(?P<quote>["'])(?P<slash>/?)"""
    r"""(?P<slug>index|about|analysis|archive|business|help|method)\.html"""
    r"""(?P<tail>[?#][^"']*)?(?P=quote)"""
)


def _rewrite_links(markup: str) -> str:
    def clean(match):
        route = "/" if match["slug"] == "index" else f"/{match['slug']}/"
        return f"{match['quote']}{route}{match['tail'] or ''}{match['quote']}"
    return _QUOTED_PAGE.sub(clean, markup)


def _canonical(markup: str, slug: str) -> str:
    url = f"{DOMAIN}/{slug}/" if slug else f"{DOMAIN}/"
    link = f'<link rel="canonical" href="{url}">'
    existing = re.compile(r'<link\s+rel=["\']canonical["\'][^>]*>', re.IGNORECASE)
    if existing.search(markup):
        return existing.sub(link, markup, count=1)
    return re.sub(r"</head>", f"  {link}\n</head>", markup, count=1, flags=re.IGNORECASE)


def _insert_at_head(markup: str, html: str) -> str:
    result, count = re.subn(r"(<head(?:\s[^>]*)?>)", lambda m: m.group(1) + "\n" + html,
                            markup, count=1, flags=re.IGNORECASE)
    if count != 1:
        raise ValueError("Не найден элемент <head> для чистого URL")
    return result


def _legacy_redirect(slug: str) -> str:
    pathname = f"/{slug}.html" if slug else "/index.html"
    target = f"/{slug}/" if slug else "/"
    # A safe, exact pathname check avoids redirects when the same index document
    # is served from the clean directory route.
    return ("<script>if(location.pathname===" + repr(pathname) +
            ")location.replace(" + repr(target) +
            "+location.search+location.hash);</script>")


def publish_clean_routes(destination: Path) -> None:
    """Produce clean aliases, root-relative navigation and backwards compatibility."""
    destination = Path(destination)

    for slug in CLEAN_ROUTES:
        source = destination / f"{slug}.html"
        original = source.read_text(encoding="utf-8")
        content = _canonical(_rewrite_links(original), slug)

        # On clean aliases, relative asset paths resolve against the domain root.
        # Turn fragment-only links into current-page URLs to avoid the base tag
        # sending users back to the home page when they follow in-page anchors.
        alias = _insert_at_head(content, '<base href="/">')
        alias = re.sub(
            r'(?P<attr>href\s*=\s*)(?P<quote>["\'])#(?P<frag>[^"\']+)(?P=quote)',
            lambda match: (match["attr"] + match["quote"] + f"/{slug}/#" +
                           match["frag"] + match["quote"]), alias,
            flags=re.IGNORECASE,
        )
        clean_dir = destination / slug
        clean_dir.mkdir(parents=True, exist_ok=True)
        (clean_dir / "index.html").write_text(alias, encoding="utf-8")

        # Keep legacy .html resources available and redirect existing bookmarks.
        legacy = _insert_at_head(content, _legacy_redirect(slug))
        source.write_text(legacy, encoding="utf-8")

    # /index.html also keeps working, but normalizes to the root homepage.
    home = destination / "index.html"
    text = _canonical(_rewrite_links(home.read_text(encoding="utf-8")), "")
    home.write_text(_insert_at_head(text, _legacy_redirect("")), encoding="utf-8")

    # The PRO chooser builds navigation cards from JavaScript, not plain HTML.
    chooser = destination / "pro-gateway.js"
    if chooser.exists():
        chooser.write_text(_rewrite_links(chooser.read_text(encoding="utf-8")),
                           encoding="utf-8")

    sitemap = destination / "sitemap.xml"
    if sitemap.exists():
        xml = sitemap.read_text(encoding="utf-8")
        xml = re.sub(
            rf"{re.escape(DOMAIN)}/(about|analysis|archive|business|help|method)\.html",
            lambda match: f"{DOMAIN}/{match.group(1)}/", xml,
        )
        sitemap.write_text(xml, encoding="utf-8")

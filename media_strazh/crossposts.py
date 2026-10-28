"""Conservative website/Telegram copies within one publisher, without deleting originals.

This is exact normalized text matching, not event clustering or teaser matching.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import unicodedata

from .analysis import VERSION
from .sources import SOURCES

VERSION_DEDUP = "crossposts-1.0"
MAX_GAP = timedelta(hours=48)
WORD = re.compile(r"[^\W_]+", re.UNICODE)
FOOTER = re.compile(r"(?:[^\w«\"]*(?:подписывайтесь|подписаться)\s+на\s+[^.!?\n]{1,110}[.!]?|"
                    r"https?://\S+|@[A-Za-z][A-Za-z0-9_]{4,31})", re.I)


def aware_date(value):
    try:
        date = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return date.astimezone(timezone.utc) if date.utcoffset() is not None else None
    except (TypeError, ValueError, AttributeError, OverflowError):
        return None


def _tokens(value):
    value = unicodedata.normalize("NFKC", value).casefold()
    value = value.translate(str.maketrans({'«': '"', '»': '"', '“': '"', '”': '"', '„': '"',
                                          '–': '-', '—': '-', '‑': '-'}))
    # Retain punctuation, numbers, negation and quote positions. Even a comma
    # can change a proposition; a bag of words or fuzzy score is insufficient.
    return tuple(re.findall(r"[^\W_]+|[^\w\s]", value, re.UNICODE))


def _body(value):
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    while len(lines) > 1 and FOOTER.fullmatch(lines[-1]):
        lines.pop()
    if lines:
        lines[0] = re.sub(r"^[⚡📰🔴🔹🔸➡👉\ufe0f\s]+", "", lines[0])
    return _tokens("\n".join(lines))


@dataclass
class _Text:
    row: dict

    def __post_init__(self):
        self.title = _tokens(self.row["title"])
        self.body = _body(self.row["text"])
        # A Telegram message often starts with the website headline; the
        # website extractor may already repeat its own headline in the body.
        self.content = self.body
        first_line = next((line.strip() for line in self.row["text"].splitlines() if line.strip()), "")
        if self.title and _tokens(first_line) == self.title and self.body[:len(self.title)] == self.title:
            self.body = self.body[len(self.title):]
        self.date = aware_date(self.row["published_at"])


def _match(left, right):
    if left.date is None or right.date is None or abs(left.date - right.date) > MAX_GAP:
        return ""
    if ((any(WORD.fullmatch(token) for token in left.body) and left.body == right.body)
            or (any(WORD.fullmatch(token) for token in left.content) and left.content == right.content)):
        return "exact_text"
    web, tg = (left, right) if SOURCES[left.row["source_id"]].platform == "website" else (right, left)
    if web.title and tg.content[:len(web.title)] == web.title:
        rest = tg.content[len(web.title):]
        # A headline-only teaser or a shorter lead remains a distinct text.
        if any(WORD.fullmatch(token) for token in rest) and rest == web.body:
            return "same_text_with_headline"
    return ""


@dataclass
class PublicationGroup:
    members: list
    method: str = ""

    @property
    def key(self):
        return "publication-" + str(min(row["id"] for row in self.members))

    @property
    def published_at(self):
        dates = [aware_date(row["published_at"]) for row in self.members]
        return min(date for date in dates if date is not None) if any(dates) else None

    @property
    def representative(self):
        return max(self.members, key=lambda row: (
            row.get("analyzed", False), row.get("finding_count", 0), len(row["text"]),
            SOURCES[row["source_id"]].platform == "website", -row["id"]))


def group_publications(rows):
    """One website + one Telegram copy, same publisher, <=48h, never transitively.

    Keeping at most one occurrence from either platform avoids chaining an
    evolving report through several superficially similar updates. Uncertain
    matches, missing dates, and different publishers remain separate.
    """
    ordered = sorted((dict(row) for row in rows), key=lambda row: (
        aware_date(row["published_at"]) or datetime.min.replace(tzinfo=timezone.utc), row["id"]))
    publishers = defaultdict(list)
    groups, features = [], {}
    platforms = defaultdict(set)
    for row in ordered:
        source = SOURCES[row["source_id"]]
        platforms[source.publisher].add(source.platform)
    for row in ordered:
        source = SOURCES[row["source_id"]]
        group = None
        if len(platforms[source.publisher]) > 1:
            current = _Text(row)
            # Scan backwards only inside the local temporal neighbourhood.
            for candidate in reversed(publishers[source.publisher]):
                other = candidate.members[0]
                date = aware_date(other["published_at"])
                if current.date and date and current.date - date > MAX_GAP:
                    break
                if len(candidate.members) > 1 or SOURCES[other["source_id"]].platform == source.platform:
                    continue
                match = _match(features[other["id"]], current)
                if match:
                    candidate.members.append(row)
                    candidate.method = match
                    group = candidate
                    break
            features[row["id"]] = current
        if group is None:
            group = PublicationGroup([row])
            groups.append(group)
            publishers[source.publisher].append(group)
    return groups


def current_publications(store, start=None, end=None, findings=False):
    """Current versions only. SQL narrows dates; Python remains the final guard."""
    marks = ",".join("?" for _ in SOURCES)
    where, params = "", [VERSION, *SOURCES]
    if start is not None:
        where += " AND julianday(r.published_at)>=julianday(?)-1.0/86400"
        params.append(start.isoformat())
    if end is not None:
        where += " AND julianday(r.published_at)<=julianday(?)+1.0/86400"
        params.append(end.isoformat())
    extra = ",json_extract(n.result_json,'$.findings') AS findings_json" if findings else ""
    return [dict(row) for row in store.db.execute("""
        SELECT a.id,a.source_id,r.id AS revision_id,r.title,r.text,r.canonical_url AS url,
               r.published_at,r.retrieved_at,(n.revision_id IS NOT NULL) AS analyzed,
               COALESCE(json_array_length(json_extract(n.result_json,'$.findings')),0) AS finding_count
        """ + extra + """
        FROM articles a JOIN revisions r ON r.id=a.current_revision_id
        LEFT JOIN analyses n ON n.revision_id=r.id AND n.algorithm_version=?
        WHERE a.source_id IN (""" + marks + ")" + where, params)]

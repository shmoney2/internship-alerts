import hashlib
import re
from datetime import datetime

from pydantic import BaseModel

COMPANY_SUFFIXES = {"inc", "llc", "ltd", "corp", "corporation", "co"}

_PUNCTUATION_RE = re.compile(r"[^\w\s+#]", re.UNICODE)
_WHITESPACE_RE = re.compile(r"\s+")


class Posting(BaseModel):
    id: str
    company: str
    title: str
    location: str
    url: str
    source: str
    posted_at: datetime | None
    raw: str


def normalize(s: str) -> str:
    s = s.lower()
    s = _PUNCTUATION_RE.sub("", s)
    s = _WHITESPACE_RE.sub(" ", s)
    return s.strip()


def _normalize_company(company: str) -> str:
    words = normalize(company).split()
    if words and words[-1] in COMPANY_SUFFIXES:
        words = words[:-1]
    return " ".join(words)


def canonical_id(company: str, title: str, location: str) -> str:
    parts = "|".join(
        [_normalize_company(company), normalize(title), normalize(location)]
    )
    return hashlib.sha256(parts.encode("utf-8")).hexdigest()[:16]

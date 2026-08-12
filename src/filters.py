import re

from src import config
from src.schema import Posting

# Complete words/phrases: match on both sides so "phd" doesn't fire on
# unrelated words, and "intern" doesn't fire inside "International".
_NEW_GRAD_FULL_TIME = re.compile(
    r"\b(new grad|new graduate|university grad|entry level|full[- ]time)\b",
    re.IGNORECASE,
)
_HAS_INTERN_WORD = re.compile(r"\bintern\b", re.IGNORECASE)

_ADVANCED_DEGREE = re.compile(r"\b(phd|ph\.d|masters only)\b", re.IGNORECASE)

# Deliberate word stems ("scien", "manag", "quant") so "data scientist",
# "product management", and "quantitative" are also caught. Only the
# leading boundary is required; the trailing side is intentionally open.
_NON_SWE = re.compile(
    r"\b(data scien|product manag|hardware|mechanical|quant|business|marketing|design)",
    re.IGNORECASE,
)

_INTERNSHIP_KEYWORDS = re.compile(r"\b(intern|internship|co-op|coop)\b", re.IGNORECASE)


def is_eligible(posting: Posting) -> bool:
    if not posting.active:
        return False

    if config.TARGET_TERM not in posting.terms:
        return False

    if posting.degrees and "Bachelor's" not in posting.degrees:
        return False

    title = posting.title

    if _NEW_GRAD_FULL_TIME.search(title) and not _HAS_INTERN_WORD.search(title):
        return False

    if _ADVANCED_DEGREE.search(title):
        return False

    if _NON_SWE.search(title):
        return False

    if _INTERNSHIP_KEYWORDS.search(title):
        return True

    return False

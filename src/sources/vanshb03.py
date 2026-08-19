import json
from datetime import datetime, timezone

import httpx

from src.schema import Posting, canonical_id

LISTINGS_URL = (
    "https://raw.githubusercontent.com/vanshb03/"
    "Summer2027-Internships/dev/.github/scripts/listings.json"
)

# vanshb03's entries carry a bare "season" (Summer/Fall/Winter/Spring) with no
# year, unlike Simplify's "Summer 2027"-style terms. Only "Summer" is
# unambiguous for this repo (Summer2027-Internships) -- Fall/Winter/Spring
# entries are dropped since their year can't be derived from the data alone.
_TARGET_SEASON = "Summer"
_TARGET_TERM = "Summer 2027"


def parse_listings(entries: list[dict]) -> list[Posting]:
    postings = []
    for entry in entries:
        if entry.get("season") != _TARGET_SEASON:
            continue
        company = entry.get("company_name")
        url = entry.get("url")
        if not company or not url:
            continue
        title = entry.get("title") or ""
        location = ", ".join(entry.get("locations") or [])
        postings.append(
            Posting(
                id=canonical_id(company, title, location),
                company=company,
                title=title,
                location=location,
                url=url,
                source="vanshb03",
                posted_at=_parse_posted_at(entry.get("date_posted")),
                first_seen_at=None,
                active=bool(entry.get("active", False)),
                terms=[_TARGET_TERM],
                degrees=[],
                raw=json.dumps(entry),
            )
        )
    return postings


def _parse_posted_at(timestamp) -> datetime | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


class Vanshb03Source:
    name = "vanshb03"

    def fetch(self) -> list[Posting]:
        response = httpx.get(LISTINGS_URL, timeout=30)
        response.raise_for_status()
        return parse_listings(response.json())

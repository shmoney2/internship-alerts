import json
from datetime import datetime, timezone

import httpx

from src.schema import Posting, canonical_id

LISTINGS_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/"
    "Summer2027-Internships/dev/.github/scripts/listings.json"
)


def parse_listings(entries: list[dict]) -> list[Posting]:
    postings = []
    for entry in entries:
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
                source="simplify",
                posted_at=_parse_posted_at(entry.get("date_posted")),
                raw=json.dumps(entry),
            )
        )
    return postings


def _parse_posted_at(timestamp) -> datetime | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


class SimplifySource:
    name = "simplify"

    def fetch(self) -> list[Posting]:
        response = httpx.get(LISTINGS_URL, timeout=30)
        response.raise_for_status()
        return parse_listings(response.json())

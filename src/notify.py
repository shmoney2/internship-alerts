import os
import time

import httpx

from src.schema import Posting

WEBHOOK_URL_ENV = "DISCORD_WEBHOOK_URL"
BATCH_SIZE = 10
SLEEP_SECONDS = 1
DISCORD_CONTENT_LIMIT = 2000


def send(postings: list[Posting]) -> list[str]:
    if not postings:
        return []

    webhook_url = os.environ[WEBHOOK_URL_ENV]
    batches = _make_batches(postings)

    sent_ids = []
    for i, batch in enumerate(batches):
        try:
            response = httpx.post(
                webhook_url, json={"content": _format_message(batch)}, timeout=10
            )
            response.raise_for_status()
        except httpx.HTTPError:
            break
        sent_ids.extend(posting.id for posting in batch)
        if i < len(batches) - 1:
            time.sleep(SLEEP_SECONDS)

    return sent_ids


def _make_batches(postings: list[Posting]) -> list[list[Posting]]:
    """Groups of up to BATCH_SIZE, closed early if adding the next posting
    would push the formatted message over Discord's content length limit."""
    batches = []
    current: list[Posting] = []
    for posting in postings:
        candidate = current + [posting]
        if current and (
            len(candidate) > BATCH_SIZE or len(_format_message(candidate)) > DISCORD_CONTENT_LIMIT
        ):
            batches.append(current)
            current = [posting]
        else:
            current = candidate
    if current:
        batches.append(current)
    return batches


def _format_message(postings: list[Posting]) -> str:
    lines = [
        f"**{posting.company}** — {posting.title} ({posting.location})\n{posting.url}"
        for posting in postings
    ]
    return "\n\n".join(lines)

import os
import time

import httpx

from src.schema import Posting

WEBHOOK_URL_ENV = "DISCORD_WEBHOOK_URL"
BATCH_SIZE = 10
SLEEP_SECONDS = 1


def send(postings: list[Posting]) -> list[str]:
    if not postings:
        return []

    webhook_url = os.environ[WEBHOOK_URL_ENV]
    batches = [postings[i : i + BATCH_SIZE] for i in range(0, len(postings), BATCH_SIZE)]

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


def _format_message(postings: list[Posting]) -> str:
    lines = [
        f"**{posting.company}** — {posting.title} ({posting.location})\n{posting.url}"
        for posting in postings
    ]
    return "\n\n".join(lines)

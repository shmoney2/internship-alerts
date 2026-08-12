import os
import time

import httpx

from src.schema import Posting

WEBHOOK_URL_ENV = "DISCORD_WEBHOOK_URL"
BATCH_SIZE = 10
SLEEP_SECONDS = 1
DISCORD_EMBED_TOTAL_LIMIT = 6000
EMBED_COLOR = 0x5865F2  # Discord blurple


def send(postings: list[Posting]) -> list[str]:
    if not postings:
        return []

    webhook_url = os.environ[WEBHOOK_URL_ENV]
    batches = _make_batches(postings)

    sent_ids = []
    for i, batch in enumerate(batches):
        try:
            embeds = [_format_embed(posting) for posting in batch]
            response = httpx.post(webhook_url, json={"embeds": embeds}, timeout=10)
            response.raise_for_status()
        except httpx.HTTPError:
            break
        sent_ids.extend(posting.id for posting in batch)
        if i < len(batches) - 1:
            time.sleep(SLEEP_SECONDS)

    return sent_ids


def _make_batches(postings: list[Posting]) -> list[list[Posting]]:
    """Groups of up to BATCH_SIZE embeds (Discord's per-message embed cap),
    closed early if adding the next embed would push the message's combined
    embed content over Discord's 6000-char total limit."""
    batches = []
    current: list[Posting] = []
    current_length = 0
    for posting in postings:
        embed_length = _embed_length(_format_embed(posting))
        if current and (
            len(current) >= BATCH_SIZE
            or current_length + embed_length > DISCORD_EMBED_TOTAL_LIMIT
        ):
            batches.append(current)
            current = []
            current_length = 0
        current.append(posting)
        current_length += embed_length
    if current:
        batches.append(current)
    return batches


def _format_embed(posting: Posting) -> dict:
    return {
        "title": posting.title,
        "url": posting.url,
        "author": {"name": posting.company},
        "color": EMBED_COLOR,
        "fields": [
            {"name": "Location", "value": posting.location, "inline": True},
            {"name": "Term", "value": ", ".join(posting.terms), "inline": True},
        ],
        "footer": {"text": _footer_text(posting)},
    }


def _footer_text(posting: Posting) -> str:
    if not posting.first_seen_at:
        return "First seen unknown"
    return f"First seen {posting.first_seen_at.strftime('%Y-%m-%d %H:%M UTC')}"


def _embed_length(embed: dict) -> int:
    """Discord's own formula for the 6000-char total-embed-content limit:
    title + description + every field's name+value + footer.text + author.name."""
    length = len(embed.get("title", "")) + len(embed.get("description", ""))
    length += len(embed.get("footer", {}).get("text", ""))
    length += len(embed.get("author", {}).get("name", ""))
    for field in embed.get("fields", []):
        length += len(field.get("name", "")) + len(field.get("value", ""))
    return length

from datetime import datetime, timezone

import httpx
import pytest

from src import notify
from src.schema import Posting, canonical_id

FIRST_SEEN_AT = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def make_posting(n: int, terms=None) -> Posting:
    company = f"Company{n}"
    title = "Software Engineer Intern"
    location = "Remote"
    return Posting(
        id=canonical_id(company, title, location) + f"-{n}",
        company=company,
        title=title,
        location=location,
        url=f"https://example.com/jobs/{n}",
        source="simplify",
        posted_at=None,
        first_seen_at=FIRST_SEEN_AT,
        active=True,
        terms=terms if terms is not None else ["Summer 2027"],
        degrees=[],
        raw="{}",
    )


def make_long_posting(n: int, location_length: int = 700) -> Posting:
    # Long in `location` (field-value cap 1024), not `title` (cap 256) --
    # this must stay a *valid* single embed while still being long enough
    # that a batch of several pushes the message over Discord's 6000-char
    # combined-embed-content limit.
    company = f"Company{n}"
    title = "Software Engineer Intern"
    location = "X" * location_length
    return Posting(
        id=canonical_id(company, title, location) + f"-{n}",
        company=company,
        title=title,
        location=location,
        url=f"https://example.com/jobs/{n}",
        source="simplify",
        posted_at=None,
        first_seen_at=FIRST_SEEN_AT,
        active=True,
        terms=["Summer 2027"],
        degrees=[],
        raw="{}",
    )


class FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            req = httpx.Request("POST", "https://discord.example/webhook")
            resp = httpx.Response(status_code=self.status_code, request=req)
            raise httpx.HTTPStatusError("bad status", request=req, response=resp)


def make_fake_post(fail_at_call=None, raise_connect_error=False):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append({"url": url, "json": json, "timeout": timeout})
        call_index = len(calls) - 1
        if fail_at_call is not None and call_index == fail_at_call:
            if raise_connect_error:
                raise httpx.ConnectError("simulated connection failure")
            return FakeResponse(status_code=500)
        return FakeResponse(status_code=200)

    fake_post.calls = calls
    return fake_post


@pytest.fixture(autouse=True)
def webhook_env(monkeypatch):
    monkeypatch.setenv(notify.WEBHOOK_URL_ENV, "https://discord.example/webhook")


@pytest.fixture(autouse=True)
def no_real_sleep(monkeypatch):
    calls = []
    monkeypatch.setattr(notify.time, "sleep", lambda seconds: calls.append(seconds))
    return calls


class TestSend:
    def test_empty_list_returns_empty_without_touching_webhook(self, monkeypatch):
        monkeypatch.delenv(notify.WEBHOOK_URL_ENV, raising=False)
        assert notify.send([]) == []

    def test_single_batch_all_sent(self, monkeypatch):
        postings = [make_posting(i) for i in range(3)]
        fake_post = make_fake_post()
        monkeypatch.setattr(httpx, "post", fake_post)

        result = notify.send(postings)

        assert result == [p.id for p in postings]
        assert len(fake_post.calls) == 1

    def test_sleep_not_called_for_single_batch(self, monkeypatch, no_real_sleep):
        postings = [make_posting(i) for i in range(3)]
        monkeypatch.setattr(httpx, "post", make_fake_post())

        notify.send(postings)

        assert no_real_sleep == []

    def test_batches_of_ten(self, monkeypatch):
        postings = [make_posting(i) for i in range(25)]
        fake_post = make_fake_post()
        monkeypatch.setattr(httpx, "post", fake_post)

        result = notify.send(postings)

        assert result == [p.id for p in postings]
        assert len(fake_post.calls) == 3

        batch_sizes = [len(call["json"]["embeds"]) for call in fake_post.calls]
        assert batch_sizes == [10, 10, 5]

    def test_sleeps_between_but_not_after_last_batch(self, monkeypatch, no_real_sleep):
        postings = [make_posting(i) for i in range(25)]
        monkeypatch.setattr(httpx, "post", make_fake_post())

        notify.send(postings)

        assert no_real_sleep == [1, 1]

    def test_mid_batch_failure_returns_only_ids_sent_before_it(self, monkeypatch):
        postings = [make_posting(i) for i in range(25)]
        fake_post = make_fake_post(fail_at_call=1)
        monkeypatch.setattr(httpx, "post", fake_post)

        result = notify.send(postings)

        assert result == [p.id for p in postings[:10]]
        assert len(fake_post.calls) == 2

    def test_mid_batch_failure_does_not_raise(self, monkeypatch):
        postings = [make_posting(i) for i in range(15)]
        monkeypatch.setattr(httpx, "post", make_fake_post(fail_at_call=1))

        notify.send(postings)  # must not raise

    def test_connection_error_returns_only_ids_sent_before_it(self, monkeypatch):
        postings = [make_posting(i) for i in range(15)]
        fake_post = make_fake_post(fail_at_call=1, raise_connect_error=True)
        monkeypatch.setattr(httpx, "post", fake_post)

        result = notify.send(postings)

        assert result == [p.id for p in postings[:10]]

    def test_first_batch_failure_returns_empty_list(self, monkeypatch):
        postings = [make_posting(i) for i in range(5)]
        monkeypatch.setattr(httpx, "post", make_fake_post(fail_at_call=0))

        result = notify.send(postings)

        assert result == []

    def test_posts_to_the_configured_webhook_url(self, monkeypatch):
        fake_post = make_fake_post()
        monkeypatch.setattr(httpx, "post", fake_post)

        notify.send([make_posting(0)])

        assert fake_post.calls[0]["url"] == "https://discord.example/webhook"

    def test_missing_webhook_env_raises(self, monkeypatch):
        monkeypatch.delenv(notify.WEBHOOK_URL_ENV, raising=False)
        with pytest.raises(KeyError):
            notify.send([make_posting(0)])


class TestFormatEmbed:
    def test_title_and_url_make_a_clickable_link(self):
        posting = make_posting(0)
        embed = notify._format_embed(posting)
        assert embed["title"] == posting.title
        assert embed["url"] == posting.url

    def test_author_is_the_company(self):
        posting = make_posting(0)
        embed = notify._format_embed(posting)
        assert embed["author"] == {"name": posting.company}

    def test_fields_are_location_and_all_terms(self):
        posting = make_posting(0, terms=["Winter 2027", "Spring 2027", "Summer 2027"])
        embed = notify._format_embed(posting)
        assert embed["fields"] == [
            {"name": "Location", "value": posting.location, "inline": True},
            {"name": "Term", "value": "Winter 2027, Spring 2027, Summer 2027", "inline": True},
        ]

    def test_footer_shows_first_seen_at(self):
        posting = make_posting(0)
        embed = notify._format_embed(posting)
        assert embed["footer"] == {"text": "First seen 2026-01-01 12:00 UTC"}

    def test_footer_handles_missing_first_seen_at(self):
        posting = make_posting(0).model_copy(update={"first_seen_at": None})
        embed = notify._format_embed(posting)
        assert embed["footer"] == {"text": "First seen unknown"}

    def test_has_a_color(self):
        posting = make_posting(0)
        embed = notify._format_embed(posting)
        assert embed["color"] == notify.EMBED_COLOR


class TestSendEmbedPayload:
    def test_sends_one_embed_per_posting_no_content_key(self, monkeypatch):
        postings = [make_posting(i) for i in range(3)]
        fake_post = make_fake_post()
        monkeypatch.setattr(httpx, "post", fake_post)

        notify.send(postings)

        payload = fake_post.calls[0]["json"]
        assert "content" not in payload
        assert len(payload["embeds"]) == 3
        assert payload["embeds"][0]["title"] == postings[0].title


class TestMakeBatches:
    def test_short_postings_still_batch_by_ten(self):
        postings = [make_posting(i) for i in range(25)]
        batches = notify._make_batches(postings)
        assert [len(b) for b in batches] == [10, 10, 5]

    def test_no_batch_exceeds_the_discord_embed_total_limit(self):
        # Long-location postings: 10-per-batch would exceed 6000 combined
        # chars, so this must split into more than one batch even though
        # each individual embed is well within every per-field cap.
        postings = [make_long_posting(i) for i in range(10)]
        batches = notify._make_batches(postings)

        assert len(batches) > 1
        for batch in batches:
            total = sum(notify._embed_length(notify._format_embed(p)) for p in batch)
            assert total <= notify.DISCORD_EMBED_TOTAL_LIMIT

    def test_length_split_batches_still_respect_batch_size_cap(self):
        postings = [make_long_posting(i) for i in range(30)]
        batches = notify._make_batches(postings)
        for batch in batches:
            assert len(batch) <= notify.BATCH_SIZE

    def test_every_posting_is_included_exactly_once(self):
        postings = [make_long_posting(i) for i in range(30)]
        batches = notify._make_batches(postings)
        flattened = [p for batch in batches for p in batch]
        assert flattened == postings

    def test_oversized_batch_no_longer_fails_against_discord_content_rules(self, monkeypatch):
        # Reproduces the real 400 seen in production: a fixed 10-per-batch
        # split put too much combined embed content in one message.
        postings = [make_long_posting(i) for i in range(10)]
        fake_post = make_fake_post()
        monkeypatch.setattr(httpx, "post", fake_post)

        result = notify.send(postings)

        assert result == [p.id for p in postings]
        assert len(fake_post.calls) > 1
        for call in fake_post.calls:
            total = sum(notify._embed_length(e) for e in call["json"]["embeds"])
            assert total <= notify.DISCORD_EMBED_TOTAL_LIMIT

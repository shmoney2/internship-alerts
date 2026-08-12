import json

import pytest

from src import config, run, store
from src.schema import Posting, canonical_id


def make_posting(
    company="Acme",
    title="Software Engineer Intern",
    active=True,
    terms=None,
    degrees=None,
) -> Posting:
    location = "Remote"
    pid = canonical_id(company, title, location)
    return Posting(
        id=pid,
        company=company,
        title=title,
        location=location,
        url=f"https://example.com/jobs/{pid}",
        source="simplify",
        posted_at=None,
        active=active,
        terms=terms if terms is not None else [config.TARGET_TERM],
        degrees=degrees if degrees is not None else [],
        raw="{}",
    )


class FakeSource:
    name = "fake"

    def __init__(self, postings=None, error=None):
        self._postings = postings or []
        self._error = error

    def fetch(self):
        if self._error is not None:
            raise self._error
        return self._postings


@pytest.fixture(autouse=True)
def isolated_metrics(tmp_path):
    return str(tmp_path / "metrics.jsonl")


class TestMainHappyPath:
    def test_full_pipeline_sends_and_marks_eligible_postings(self, monkeypatch, isolated_metrics):
        postings = [make_posting(company="Acme"), make_posting(company="Beta")]
        sent_ids = []

        def fake_send(eligible):
            sent_ids.extend(p.id for p in eligible)
            return [p.id for p in eligible]

        monkeypatch.setattr(run, "send", fake_send)

        record = run.main(
            source=FakeSource(postings), metrics_path=isolated_metrics, db_path=":memory:"
        )

        assert record["fetched"] == 2
        assert record["new"] == 2
        assert record["eligible"] == 2
        assert record["alerted"] == 2
        assert sent_ids == [p.id for p in postings]
        assert store.get_unalerted() == []

    def test_ineligible_postings_are_not_sent_or_marked(self, monkeypatch, isolated_metrics):
        ineligible = make_posting(company="Acme", active=False)
        send_calls = []
        monkeypatch.setattr(run, "send", lambda eligible: send_calls.append(eligible) or [])

        record = run.main(
            source=FakeSource([ineligible]), metrics_path=isolated_metrics, db_path=":memory:"
        )

        assert record["eligible"] == 0
        assert record["alerted"] == 0
        assert send_calls == [[]]
        assert len(store.get_unalerted()) == 1

    def test_previously_unalerted_postings_are_retried_even_with_no_new_fetch(
        self, monkeypatch, tmp_path
    ):
        # ":memory:" opens a fresh empty db on every init_db() call, so
        # retry-across-runs needs a real file to carry state between them.
        db_path = str(tmp_path / "run_test.db")
        metrics_path = str(tmp_path / "metrics.jsonl")

        store.init_db(db_path)
        stale = make_posting(company="Acme")
        store.upsert([stale])

        sent_ids = []
        monkeypatch.setattr(
            run, "send", lambda eligible: sent_ids.extend(p.id for p in eligible) or sent_ids
        )

        record = run.main(source=FakeSource([]), metrics_path=metrics_path, db_path=db_path)

        assert record["fetched"] == 0
        assert record["new"] == 0
        assert record["eligible"] == 1
        assert record["alerted"] == 1
        assert sent_ids == [stale.id]
        assert store.get_unalerted() == []

    def test_partial_notify_failure_only_marks_sent_ids(self, monkeypatch, isolated_metrics):
        p1 = make_posting(company="Acme")
        p2 = make_posting(company="Beta")
        monkeypatch.setattr(run, "send", lambda eligible: [eligible[0].id])

        record = run.main(
            source=FakeSource([p1, p2]), metrics_path=isolated_metrics, db_path=":memory:"
        )

        assert record["alerted"] == 1
        remaining = store.get_unalerted()
        assert [p.id for p in remaining] == [p2.id]

    def test_metrics_are_appended_to_file(self, monkeypatch, isolated_metrics):
        monkeypatch.setattr(run, "send", lambda eligible: [p.id for p in eligible])

        run.main(source=FakeSource([]), metrics_path=isolated_metrics, db_path=":memory:")
        run.main(source=FakeSource([]), metrics_path=isolated_metrics, db_path=":memory:")

        with open(isolated_metrics, encoding="utf-8") as f:
            lines = f.readlines()

        assert len(lines) == 2
        record = json.loads(lines[0])
        assert set(record.keys()) == {"timestamp", "fetched", "new", "eligible", "alerted", "duration"}


class TestMainFetchFailure:
    def test_fetch_failure_does_not_raise_and_returns_zero_counts(
        self, monkeypatch, isolated_metrics
    ):
        monkeypatch.setattr(run, "send", lambda eligible: [p.id for p in eligible])

        record = run.main(
            source=FakeSource(error=ConnectionError("boom")),
            metrics_path=isolated_metrics,
            db_path=":memory:",
        )

        assert record == {
            "timestamp": record["timestamp"],
            "fetched": 0,
            "new": 0,
            "eligible": 0,
            "alerted": 0,
            "duration": record["duration"],
        }

    def test_fetch_failure_still_logs_a_metrics_row(self, monkeypatch, isolated_metrics):
        monkeypatch.setattr(run, "send", lambda eligible: [p.id for p in eligible])

        run.main(
            source=FakeSource(error=RuntimeError("boom")),
            metrics_path=isolated_metrics,
            db_path=":memory:",
        )

        with open(isolated_metrics, encoding="utf-8") as f:
            lines = f.readlines()
        assert len(lines) == 1
        assert json.loads(lines[0])["fetched"] == 0

    def test_fetch_failure_does_not_call_send(self, monkeypatch, isolated_metrics):
        called = []
        monkeypatch.setattr(run, "send", lambda eligible: called.append(eligible) or [])

        run.main(
            source=FakeSource(error=RuntimeError("boom")),
            metrics_path=isolated_metrics,
            db_path=":memory:",
        )

        assert called == []

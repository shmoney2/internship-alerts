from src.schema import Posting, canonical_id
from src.sources.composite import CompositeSource


def make_posting(company: str) -> Posting:
    location = "Remote"
    pid = canonical_id(company, "SWE Intern", location)
    return Posting(
        id=pid,
        company=company,
        title="SWE Intern",
        location=location,
        url=f"https://example.com/{pid}",
        source="fake",
        posted_at=None,
        first_seen_at=None,
        active=True,
        terms=["Summer 2027"],
        degrees=[],
        raw="{}",
    )


class FakeSource:
    def __init__(self, name, postings=None, error=None):
        self.name = name
        self._postings = postings or []
        self._error = error

    def fetch(self):
        if self._error is not None:
            raise self._error
        return self._postings


class TestCompositeSource:
    def test_aggregates_postings_from_all_sources(self):
        a = FakeSource("a", [make_posting("Acme")])
        b = FakeSource("b", [make_posting("Beta")])

        postings = CompositeSource([a, b]).fetch()

        assert [p.company for p in postings] == ["Acme", "Beta"]

    def test_one_source_failing_does_not_drop_the_others(self):
        good = FakeSource("good", [make_posting("Acme")])
        bad = FakeSource("bad", error=RuntimeError("boom"))

        postings = CompositeSource([bad, good]).fetch()

        assert [p.company for p in postings] == ["Acme"]

    def test_all_sources_failing_returns_empty_list(self):
        bad1 = FakeSource("bad1", error=RuntimeError("boom"))
        bad2 = FakeSource("bad2", error=ConnectionError("boom"))

        assert CompositeSource([bad1, bad2]).fetch() == []

    def test_empty_source_list_returns_empty(self):
        assert CompositeSource([]).fetch() == []

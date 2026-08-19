import json
from datetime import datetime, timezone
from pathlib import Path

from src.schema import canonical_id
from src.sources.vanshb03 import Vanshb03Source, parse_listings

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "vanshb03.json"


def load_fixture() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestParseListingsAgainstFixture:
    """
    tests/fixtures/vanshb03.json is a real, unmodified 60-entry slice pulled
    directly from vanshb03/Summer2027-Internships' live listings.json. 57 of
    the 60 entries have season "Winter" and are dropped; the remaining 3
    (indices 57-59, all Point72) have season "Summer" and are expected to
    parse into Postings.
    """

    def test_returns_exact_known_count(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        assert len(entries) == 60
        assert len(postings) == 3

    def test_first_summer_entry_fields_are_correct(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        first = postings[0]
        assert first.company == "Point72"
        assert first.title == "Quantitative Developer Intern"
        assert first.location == "New York, NY"
        assert (
            first.url
            == "https://careers.point72.com/CSJobDetail?jobName=summer-2027-quantitative-developer-internship&jobCode=CSS-0012293"
        )
        assert first.source == "vanshb03"
        assert first.posted_at == datetime(2026, 4, 19, 16, 54, 58, tzinfo=timezone.utc)
        assert first.active is True
        assert first.terms == ["Summer 2027"]
        assert first.degrees == []

    def test_multi_location_summer_entry_is_comma_joined(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        last = postings[-1]
        assert last.company == "Point72"
        assert last.title == "Investment Analyst Intern, Point72 Academy"
        assert last.location == "New York, NY, San Francisco, CA, Chicago, IL, West Palm Beach, FL, Miami, FL"

    def test_id_is_canonical_not_source_id(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        summer_entries = [e for e in entries if e.get("season") == "Summer"]
        first_entry, first_posting = summer_entries[0], postings[0]
        assert first_posting.id != first_entry["id"]
        assert first_posting.id == canonical_id(
            first_entry["company_name"], first_entry["title"], first_posting.location
        )

    def test_raw_preserves_original_entry(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        summer_entries = [e for e in entries if e.get("season") == "Summer"]
        assert json.loads(postings[0].raw) == summer_entries[0]

    def test_winter_entries_are_dropped(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        assert all(p.company != "Rippling" for p in postings)


class TestParseListingsSkipLogic:
    def test_skips_non_summer_season(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1", "season": "Fall"},
            {"company_name": "Beta", "title": "SWE Intern", "url": "https://a.com/2", "season": "Summer"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1
        assert postings[0].company == "Beta"

    def test_skips_entry_missing_season_key(self):
        entries = [{"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1"}]
        assert parse_listings(entries) == []

    def test_skips_summer_entry_missing_company_name(self):
        entries = [
            {"company_name": "", "title": "SWE Intern", "url": "https://a.com/1", "season": "Summer"},
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/2", "season": "Summer"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1
        assert postings[0].company == "Acme"

    def test_skips_summer_entry_missing_url(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern", "url": "", "season": "Summer"},
            {"company_name": "Beta", "title": "SWE Intern", "url": "https://a.com/2", "season": "Summer"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1
        assert postings[0].company == "Beta"

    def test_empty_entry_list_returns_empty(self):
        assert parse_listings([]) == []

    def test_missing_locations_becomes_empty_string(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1", "season": "Summer"}
        ]
        postings = parse_listings(entries)
        assert postings[0].location == ""

    def test_missing_date_posted_becomes_none(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1", "season": "Summer"}
        ]
        postings = parse_listings(entries)
        assert postings[0].posted_at is None

    def test_missing_active_defaults_false_terms_and_degrees_are_fixed(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1", "season": "Summer"}
        ]
        postings = parse_listings(entries)
        assert postings[0].active is False
        assert postings[0].terms == ["Summer 2027"]
        assert postings[0].degrees == []


class TestVanshb03Source:
    def test_name_is_vanshb03(self):
        assert Vanshb03Source.name == "vanshb03"

    def test_fetch_calls_httpx_and_parses_response(self, monkeypatch):
        called_with = {}

        class FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return [
                    {
                        "company_name": "Acme",
                        "title": "SWE Intern",
                        "url": "https://a.com/1",
                        "locations": ["Remote"],
                        "date_posted": 1700000000,
                        "id": "source-uuid",
                        "season": "Summer",
                    }
                ]

        def fake_get(url, timeout=None):
            called_with["url"] = url
            called_with["timeout"] = timeout
            return FakeResponse()

        monkeypatch.setattr("src.sources.vanshb03.httpx.get", fake_get)

        postings = Vanshb03Source().fetch()

        assert called_with["url"].startswith("https://raw.githubusercontent.com/vanshb03/")
        assert len(postings) == 1
        assert postings[0].company == "Acme"

import json
from datetime import datetime, timezone
from pathlib import Path

from src.schema import canonical_id
from src.sources.simplify import SimplifySource, parse_listings

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "simplify.json"


def load_fixture() -> list[dict]:
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        return json.load(f)


class TestParseListingsAgainstFixture:
    """
    tests/fixtures/simplify.json is a real, unmodified 60-entry slice pulled
    directly from SimplifyJobs/Summer2027-Internships' live listings.json.
    None of the sampled entries happen to be missing company_name or url, so
    every entry is expected to parse into a Posting.
    """

    def test_returns_exact_known_count(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        assert len(entries) == 60
        assert len(postings) == 60

    def test_first_entry_fields_are_correct(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        first = postings[0]
        assert first.company == "GE Vernova"
        assert first.title == "Controls Product Management Cost Analyst Intern"
        assert first.location == "Longmont, CO, Greenville, SC"
        assert (
            first.url
            == "https://gevernova.wd5.myworkdayjobs.com/only_confidential_executive_recruiting/job/Longmont/Controls-Product-Management-Cost-Analyst-Intern_R5021234-1"
        )
        assert first.source == "simplify"
        assert first.posted_at == datetime(2025, 12, 15, 21, 36, 58, tzinfo=timezone.utc)

    def test_second_entry_fields_are_correct(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        second = postings[1]
        assert second.company == "Altom Transport"
        assert second.title == "Software Development Intern"
        assert second.location == "Markham, IL"
        assert second.posted_at == datetime(2025, 12, 17, 23, 9, 41, tzinfo=timezone.utc)

    def test_id_is_canonical_not_source_id(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        first_entry, first_posting = entries[0], postings[0]
        assert first_posting.id != first_entry["id"]
        assert first_posting.id == canonical_id(
            first_entry["company_name"], first_entry["title"], first_posting.location
        )

    def test_raw_preserves_original_entry(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        assert json.loads(postings[0].raw) == entries[0]

    def test_multi_location_entries_are_comma_joined(self):
        entries = load_fixture()
        postings = parse_listings(entries)
        multi = [p for p in postings if "," in p.location]
        assert len(multi) > 0


class TestParseListingsSkipLogic:
    def test_skips_entry_missing_company_name(self):
        entries = [
            {"company_name": "", "title": "SWE Intern", "url": "https://a.com/1"},
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/2"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1
        assert postings[0].company == "Acme"

    def test_skips_entry_with_missing_company_name_key(self):
        entries = [
            {"title": "SWE Intern", "url": "https://a.com/1"},
            {"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/2"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1

    def test_skips_entry_missing_url(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern", "url": ""},
            {"company_name": "Beta", "title": "SWE Intern", "url": "https://a.com/2"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1
        assert postings[0].company == "Beta"

    def test_skips_entry_with_missing_url_key(self):
        entries = [
            {"company_name": "Acme", "title": "SWE Intern"},
            {"company_name": "Beta", "title": "SWE Intern", "url": "https://a.com/2"},
        ]
        postings = parse_listings(entries)
        assert len(postings) == 1

    def test_empty_entry_list_returns_empty(self):
        assert parse_listings([]) == []

    def test_missing_locations_becomes_empty_string(self):
        entries = [{"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1"}]
        postings = parse_listings(entries)
        assert postings[0].location == ""

    def test_missing_date_posted_becomes_none(self):
        entries = [{"company_name": "Acme", "title": "SWE Intern", "url": "https://a.com/1"}]
        postings = parse_listings(entries)
        assert postings[0].posted_at is None


class TestSimplifySource:
    def test_name_is_simplify(self):
        assert SimplifySource.name == "simplify"

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
                    }
                ]

        def fake_get(url, timeout=None):
            called_with["url"] = url
            called_with["timeout"] = timeout
            return FakeResponse()

        monkeypatch.setattr("src.sources.simplify.httpx.get", fake_get)

        postings = SimplifySource().fetch()

        assert called_with["url"].startswith("https://raw.githubusercontent.com/SimplifyJobs/")
        assert len(postings) == 1
        assert postings[0].company == "Acme"

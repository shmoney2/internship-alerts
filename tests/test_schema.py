from datetime import datetime

import pytest

from src.schema import Posting, canonical_id, normalize


class TestNormalize:
    def test_empty_string(self):
        assert normalize("") == ""

    def test_whitespace_only(self):
        assert normalize("   \t\n  ") == ""

    def test_lowercases(self):
        assert normalize("Software Engineer") == "software engineer"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize("  Acme  ") == "acme"

    def test_collapses_internal_whitespace(self):
        assert normalize("Acme    Corp\tSoftware") == "acme corp software"

    def test_strips_punctuation(self):
        assert normalize("Acme, Inc.") == "acme inc"

    def test_strips_punctuation_no_surrounding_space(self):
        assert normalize("R&D") == "rd"

    def test_preserves_plus(self):
        assert normalize("C++ Engineer") == "c++ engineer"

    def test_preserves_hash(self):
        assert normalize("C# Engineer") == "c# engineer"

    def test_unicode_letters_preserved(self):
        assert normalize("Café Software") == "café software"

    def test_unicode_punctuation_stripped(self):
        assert normalize("Foo—Bar") == "foobar"

    def test_parentheses_stripped(self):
        assert normalize("Intern (Summer 2027)") == "intern summer 2027"


class TestCanonicalId:
    def test_returns_16_char_hex_string(self):
        result = canonical_id("Acme", "SWE Intern", "Remote")
        assert len(result) == 16
        int(result, 16)  # raises if not valid hex

    def test_deterministic(self):
        a = canonical_id("Acme", "SWE Intern", "Remote")
        b = canonical_id("Acme", "SWE Intern", "Remote")
        assert a == b

    def test_different_inputs_produce_different_ids(self):
        a = canonical_id("Acme", "SWE Intern", "Remote")
        b = canonical_id("Beta", "SWE Intern", "Remote")
        assert a != b

    def test_acme_inc_collapses_with_acme(self):
        a = canonical_id("Acme, Inc.", "SWE Intern", "Remote")
        b = canonical_id("acme", "SWE Intern", "Remote")
        assert a == b

    @pytest.mark.parametrize(
        "suffixed",
        ["Acme LLC", "Acme Ltd", "Acme Corp", "Acme Corporation", "Acme Co", "Acme Co."],
    )
    def test_legal_suffixes_stripped(self, suffixed):
        a = canonical_id(suffixed, "SWE Intern", "Remote")
        b = canonical_id("Acme", "SWE Intern", "Remote")
        assert a == b

    def test_suffix_only_stripped_from_company_not_title(self):
        a = canonical_id("Acme", "SWE Intern Co", "Remote")
        b = canonical_id("Acme", "SWE Intern", "Remote")
        assert a != b

    def test_case_and_whitespace_insensitive(self):
        a = canonical_id("  ACME  ", "  SWE   Intern  ", "  Remote  ")
        b = canonical_id("acme", "swe intern", "remote")
        assert a == b


class TestPosting:
    def test_constructs_with_all_fields(self):
        p = Posting(
            id="abc123",
            company="Acme",
            title="SWE Intern",
            location="Remote",
            url="https://example.com/job",
            source="simplify",
            posted_at=datetime(2026, 1, 1),
            active=True,
            terms=["Summer 2027"],
            degrees=[],
            raw="{}",
        )
        assert p.company == "Acme"
        assert p.posted_at == datetime(2026, 1, 1)

    def test_posted_at_accepts_none(self):
        p = Posting(
            id="abc123",
            company="Acme",
            title="SWE Intern",
            location="Remote",
            url="https://example.com/job",
            source="simplify",
            posted_at=None,
            active=True,
            terms=["Summer 2027"],
            degrees=[],
            raw="{}",
        )
        assert p.posted_at is None

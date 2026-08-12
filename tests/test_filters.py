import pytest

from src import config
from src.filters import is_eligible
from src.schema import Posting, canonical_id


def make_posting(title: str, active=True, terms=None, degrees=None) -> Posting:
    company = "Acme"
    location = "Remote"
    return Posting(
        id=canonical_id(company, title, location),
        company=company,
        title=title,
        location=location,
        url="https://example.com/job",
        source="simplify",
        posted_at=None,
        active=active,
        terms=terms if terms is not None else [config.TARGET_TERM],
        degrees=degrees if degrees is not None else [],
        raw="{}",
    )


# (title, expected eligibility, why — noted only for the non-obvious cases)
LABELED_TITLES = [
    # --- clear positives ---
    ("Software Engineer Intern", True, None),
    ("Software Engineering Intern - Summer 2027", True, None),
    ("SWE Intern", True, None),
    ("Backend Engineering Co-op", True, None),
    ("Frontend Developer Internship", True, None),
    ("iOS Engineering Coop Program", True, None),
    ("Machine Learning Software Engineering Intern", True, None),
    ("Cloud Infrastructure Intern", True, None),
    ("Site Reliability Engineering Intern", True, None),
    ("Full Stack Software Engineering Intern", True, None),
    ("DevOps Engineering Intern", True, None),
    ("Security Engineering Intern", True, None),
    ("SOFTWARE ENGINEER INTERN", True, "case-insensitive matching"),
    (
        "Software Development Intern - New Grad Track 2027",
        True,
        "matches the new-grad reject pattern, but the literal word "
        "'intern' is also present, so rule 1's exception applies",
    ),
    # --- given tricky negatives from SPEC.md ---
    ("Software Engineer, New Grad 2027", False, "new-grad reject, no 'intern' present"),
    (
        "Data Science Intern",
        False,
        "the non-SWE reject rule runs before the intern-accept rule, "
        "so 'data scien' rejects this despite containing 'intern'",
    ),
    (
        "International Software Engineer",
        False,
        "word-boundary check: 'intern' must not match inside 'International'",
    ),
    # --- more tricky negatives ---
    ("PhD Research Intern", False, "advanced-degree reject has no intern exception"),
    ("Full-Time Software Engineer", False, "hyphenated full-time variant"),
    ("Full Time Software Engineer", False, "spaced full time variant"),
    (
        "Product Management Intern",
        False,
        "non-SWE reject ('product manag') fires before the intern accept, "
        "same ordering trap as Data Science Intern above",
    ),
    ("Hardware Engineering Intern", False, "non-SWE reject: hardware"),
    ("Marketing Intern", False, "non-SWE reject: marketing"),
    ("UX Design Intern", False, "non-SWE reject: design"),
    (
        "Quantitative Trading Intern",
        False,
        "'quant' is a deliberate stem, so it also matches 'Quantitative'",
    ),
    ("Business Development Intern", False, "non-SWE reject: business"),
    ("Mechanical Engineering Intern", False, "non-SWE reject: mechanical"),
    ("Entry Level Software Engineer", False, "entry-level reject, no 'intern' present"),
    ("University Grad Software Engineer", False, "university-grad reject"),
    (
        "New Graduate Software Engineering Internship 2027",
        False,
        "rule 1's exception only checks the exact word 'intern' (per spec "
        "wording); 'internship' doesn't satisfy \\bintern\\b, so the "
        "new-graduate reject still fires",
    ),
    (
        "Software Engineer Intern - Quantitative Trading Platform",
        False,
        "looks like a legitimate SWE intern title, but the non-SWE 'quant' "
        "stem still rejects it",
    ),
    ("phd research intern", False, "case-insensitive matching on the reject side too"),
    ("Masters Only Software Engineering Position", False, "advanced-degree reject: masters only"),
    ("Senior Software Engineer", False, "no intern keyword at all, falls through to default reject"),
    ("Product Manager", False, "non-SWE reject: product manag"),
    (
        "Internal Tools Software Engineer",
        False,
        "word-boundary check: 'intern' must not match inside 'Internal', "
        "and there's no other accept keyword either",
    ),
]


class TestIsEligible:
    @pytest.mark.parametrize("title,expected,reason", LABELED_TITLES)
    def test_labeled_title(self, title, expected, reason):
        posting = make_posting(title)
        assert is_eligible(posting) is expected, reason

    def test_table_has_at_least_25_entries(self):
        assert len(LABELED_TITLES) >= 25

    def test_table_has_at_least_5_tricky_negatives(self):
        negatives = [t for t in LABELED_TITLES if t[1] is False and t[2] is not None]
        assert len(negatives) >= 5


# (active, terms, degrees, expected, why) — title is always "Software Engineer
# Intern" so rules 4-8 never fire; these isolate rules 1-3 only. Several are
# drawn directly from tests/fixtures/simplify.json (indices noted below).
STRUCTURAL_CASES = [
    (True, ["Summer 2027"], [], True, "clearly eligible baseline"),
    (True, ["Summer 2027"], ["Bachelor's"], True, "Bachelor's explicitly listed"),
    (
        True,
        ["Summer 2027"],
        ["Bachelor's", "Master's", "PhD"],
        True,
        "Bachelor's among options despite PhD also listed",
    ),
    (
        False,
        ["Spring 2026"],
        [],
        False,
        "fixture[0] GE Vernova: inactive listing rejected regardless of term/degree",
    ),
    (
        False,
        [
            "Winter 2027", "Spring 2027", "Summer 2027", "Fall 2027",
            "Winter 2028", "Spring 2028", "Summer 2028", "Fall 2028",
            "Winter 2029", "Spring 2029", "Summer 2029",
        ],
        [],
        False,
        "fixture[41] T. Rowe Price: terms include Summer 2027, but inactive",
    ),
    (
        True,
        ["Spring 2026"],
        ["PhD"],
        False,
        "fixture[7] ByteDance Research Scientist: active, but wrong term "
        "(Spring 2026, not Summer 2027)",
    ),
    (
        True,
        ["Summer 2027"],
        ["PhD"],
        False,
        "fixture[58] ByteDance AI Perception Intern: active and correct term, "
        "but PhD-only degrees with no Bachelor's option",
    ),
    (True, ["Summer 2027"], ["Master's"], False, "Master's-only, no Bachelor's option"),
    (True, ["Summer 2027"], ["Master's", "PhD"], False, "grad-only, no Bachelor's option"),
    (True, [], [], False, "empty terms list never matches TARGET_TERM"),
    (True, ["Summer 2026"], [], False, "right season, wrong year"),
    (True, ["Fall 2027"], [], False, "right year, wrong season"),
]


class TestIsEligibleStructuralRules:
    @pytest.mark.parametrize("active,terms,degrees,expected,reason", STRUCTURAL_CASES)
    def test_structural_case(self, active, terms, degrees, expected, reason):
        posting = make_posting(
            "Software Engineer Intern", active=active, terms=terms, degrees=degrees
        )
        assert is_eligible(posting) is expected, reason

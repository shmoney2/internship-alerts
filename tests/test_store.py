import pytest

from src import store
from src.schema import Posting, canonical_id


def make_posting(
    company="Acme",
    title="Software Engineer Intern",
    location="Remote",
    url=None,
    source="simplify",
    posted_at=None,
    first_seen_at=None,
    active=True,
    terms=None,
    degrees=None,
    raw="{}",
    id=None,
):
    pid = id if id is not None else canonical_id(company, title, location)
    if url is None:
        url = f"https://example.com/jobs/{pid}"
    return Posting(
        id=pid,
        company=company,
        title=title,
        location=location,
        url=url,
        source=source,
        posted_at=posted_at,
        first_seen_at=first_seen_at,
        active=active,
        terms=terms if terms is not None else ["Summer 2027"],
        degrees=degrees if degrees is not None else [],
        raw=raw,
    )


@pytest.fixture(autouse=True)
def fresh_db():
    store.init_db(":memory:")
    yield


class TestInitDb:
    def test_creates_table_idempotently_on_same_file(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        store.init_db(db_path)
        p = make_posting(company="Acme")
        store.upsert([p])

        # Reconnecting to the same file must not wipe existing data.
        store.init_db(db_path)
        [stored] = store.get_unalerted()
        # first_seen_at is assigned by the store itself, so it won't match
        # the original never-stored posting's None -- compare everything else.
        assert stored.model_copy(update={"first_seen_at": None}) == p


class TestUpsert:
    def test_empty_list_returns_empty(self):
        assert store.upsert([]) == []

    def test_new_postings_are_all_returned(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        p2 = make_posting(company="Beta", title="SWE Intern")
        result = store.upsert([p1, p2])
        assert result == [p1, p2]

    def test_same_batch_upserted_twice_returns_empty_second_time(self):
        batch = [
            make_posting(company="Acme", title="SWE Intern"),
            make_posting(company="Beta", title="SWE Intern"),
        ]
        first = store.upsert(batch)
        second = store.upsert(batch)
        assert len(first) == 2
        assert second == []

    def test_partial_overlap_returns_only_the_new_ones(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        p2 = make_posting(company="Beta", title="SWE Intern")
        p3 = make_posting(company="Gamma", title="SWE Intern")
        store.upsert([p1, p2])
        result = store.upsert([p2, p3])
        assert result == [p3]

    def test_active_terms_degrees_round_trip_through_the_database(self):
        p = make_posting(
            company="Acme",
            active=False,
            terms=["Summer 2027", "Fall 2027"],
            degrees=["Master's", "PhD"],
        )
        store.upsert([p])
        [stored] = store.get_unalerted()
        assert stored.active is False
        assert stored.terms == ["Summer 2027", "Fall 2027"]
        assert stored.degrees == ["Master's", "PhD"]

    def test_first_seen_at_is_assigned_by_the_store_not_the_caller(self):
        # first_seen_at is None on a freshly-parsed posting -- the store is
        # the sole authority on "when did we first see this," computed at
        # insert time, never trusted from the caller.
        p = make_posting(company="Acme", first_seen_at=None)
        store.upsert([p])
        [stored] = store.get_unalerted()
        assert stored.first_seen_at is not None

    def test_existing_row_is_never_overwritten(self):
        original = make_posting(
            id="dup1", company="Original Co", url="https://example.com/original"
        )
        store.upsert([original])

        conflicting = make_posting(
            id="dup1", company="Changed Co", url="https://example.com/changed"
        )
        result = store.upsert([conflicting])

        assert result == []
        [stored] = store.get_unalerted()
        assert stored.company == "Original Co"
        assert stored.url == "https://example.com/original"


class TestGetUnalerted:
    def test_empty_db_returns_empty_list(self):
        assert store.get_unalerted() == []

    def test_returns_all_postings_before_any_alert(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        p2 = make_posting(company="Beta", title="SWE Intern")
        store.upsert([p1, p2])
        result = store.get_unalerted()
        assert {p.id for p in result} == {p1.id, p2.id}

    def test_excludes_alerted_postings(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        p2 = make_posting(company="Beta", title="SWE Intern")
        store.upsert([p1, p2])
        store.mark_alerted([p1.id])
        result = store.get_unalerted()
        assert [p.id for p in result] == [p2.id]


class TestMarkAlerted:
    def test_marks_given_ids_as_alerted(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        store.upsert([p1])
        store.mark_alerted([p1.id])
        assert store.get_unalerted() == []

    def test_empty_list_is_a_noop(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        store.upsert([p1])
        store.mark_alerted([])
        assert len(store.get_unalerted()) == 1

    def test_unknown_id_does_not_raise(self):
        store.mark_alerted(["nonexistent-id"])

    def test_does_not_affect_other_postings(self):
        p1 = make_posting(company="Acme", title="SWE Intern")
        p2 = make_posting(company="Beta", title="SWE Intern")
        store.upsert([p1, p2])
        store.mark_alerted([p1.id])
        remaining = store.get_unalerted()
        assert [p.id for p in remaining] == [p2.id]


class TestUninitialized:
    def test_functions_raise_before_init_db_called(self, monkeypatch):
        monkeypatch.setattr(store, "_conn", None)
        with pytest.raises(RuntimeError):
            store.get_unalerted()

# AGENTS.md

Rules for agents working in this repo. Read before making any change.

## What this project is

A scheduled job that discovers new SWE internship postings and alerts a Discord channel.
It never submits applications. If a task seems to require automated application
submission, stop and escalate.

## Definition of done

A change is done when **all** of these hold:

1. `pytest` passes
2. The specific behavior changed is covered by a test that would fail without the change
3. For any source adapter change: the fixture test asserts a **specific non-zero count**
   and spot-checks at least two field values
4. You have run the affected code path and pasted the actual output into your summary

"The code compiles" and "the tests pass" are not sufficient on their own. Unit tests
passing while the feature is broken is the most common failure mode in this repo.

## The empty-list rule

A source adapter that returns `[]` is indistinguishable from a working adapter with no
new postings. This is the single most dangerous bug class here.

Therefore:
- Never write a test that only asserts `len(result) >= 0` or `result is not None`
- Fixture tests assert exact expected counts
- If you change parsing logic, re-run against the fixture and report the count before
  and after

## Fixtures

Fixtures in `tests/fixtures/` are real captured responses. Do not regenerate, edit, or
"fix" a fixture to make a test pass. If a fixture appears wrong, escalate — a fixture
mismatch usually means the parsing is wrong, not the fixture.

Never hit the live network in tests.

## Escalate to the human, don't decide

Stop and ask when a change would:
- Alter the canonical ID scheme (it invalidates every stored row)
- Add or remove a filter rule in `filters.py`
- Change what counts as "eligible"
- Add a new dependency
- Add a new source adapter not already in the spec
- Touch anything related to submitting applications

These are product decisions. Implement them when told; do not choose them.

## Scope discipline

Implement what the task says. Do not:
- Add abstraction layers for anticipated future needs
- Add LLM calls, retries, caching, or config systems not in the spec
- Refactor adjacent code you were not asked to touch
- Add a web framework, ORM, or task queue

The spec has an explicit deferred list. Respect it.

## Review

Code review runs in a **fresh context**, not in the session that wrote the code. A
reviewing agent must not assume existing behavior was intended — check it against
SPEC.md.

## Commits

Conventional commits. One logical change per commit. Never commit the SQLite file
manually, never commit `.env`, never commit a webhook URL.

# Internship Alert System — v1 Spec

## Goal

Notify me within minutes when a new SWE internship posting appears, so I can apply
before the flood. Track everything seen in a local database.

**Non-goal:** this system never submits an application. Discovery and tracking only.

**Definition of success for v1:** runs unattended for 7 consecutive days on a cloud
host, and alerts me to at least one posting I would not have found that day on my own,
with zero duplicate alerts.

## Scope

**In scope for v1**
- One source: the SimplifyJobs Summer 2027 internship listings repo (open data, JSON)
- Dedupe against previously-seen postings
- Eligibility filter (class year, role type, location)
- Discord webhook alert
- SQLite persistence
- Scheduled execution on a cloud host

**Explicitly deferred to v2+**
- LLM extraction of unstructured postings
- Greenhouse / Lever / company career page adapters
- Eval harness
- Multi-user support and per-user filters
- Web dashboard

Do not build deferred items. Do not add abstraction layers "for later."

## Stack

- Python 3.11+
- `httpx` for HTTP
- `sqlite3` (stdlib) for storage
- `pydantic` for the schema
- `pytest` for tests
- GitHub Actions cron for scheduling (no server to manage, free)

No ORM. No web framework. No task queue.

## Data model

Single table `postings`:

| column | type | notes |
|---|---|---|
| `id` | TEXT PK | canonical ID, see below |
| `company` | TEXT | normalized, see below |
| `title` | TEXT | as published |
| `location` | TEXT | as published, may be "Remote" or multiple |
| `url` | TEXT | application link |
| `source` | TEXT | adapter name, e.g. `simplify` |
| `posted_at` | TEXT | ISO8601, source-provided if available |
| `active` | INTEGER | 1/0, source's `active` flag at time of ingestion |
| `terms` | TEXT | JSON-encoded list of term strings, e.g. `["Summer 2027"]` |
| `degrees` | TEXT | JSON-encoded list of accepted degree levels; `[]` = no restriction |
| `first_seen_at` | TEXT | ISO8601, when we first ingested it |
| `alerted_at` | TEXT NULL | ISO8601, when we sent an alert. NULL = never alerted |
| `raw` | TEXT | original JSON blob from source |

`alerted_at` is what prevents duplicate alerts. It is set only after a successful
Discord send.

### Canonical ID

`sha256(normalized_company + "|" + normalized_title + "|" + normalized_location)[:16]`

Normalization for all three fields:
- lowercase
- strip whitespace
- collapse internal runs of whitespace to a single space
- strip punctuation except `+` and `#` (preserves "C++", "C#")

Company normalization additionally strips a trailing legal suffix:
`inc`, `inc.`, `llc`, `ltd`, `corp`, `corporation`, `co`, `co.`

**Do not use the source's own ID as the canonical ID.** Sources reuse and renumber IDs,
and v2 will add sources that describe the same posting differently. The canonical ID
must be derivable from content alone.

## Modules

Each module is independently testable. Nothing imports upward.

```
src/
  schema.py      # Posting pydantic model, normalize(), canonical_id()
  sources/
    base.py      # Source protocol
    simplify.py  # SimplifyJobs adapter
  store.py       # SQLite: init, upsert, mark_alerted, get_unalerted
  filters.py     # eligibility predicate
  notify.py      # Discord webhook sender
  run.py         # entrypoint: fetch -> upsert -> filter -> notify -> mark
```

### `schema.py`

```python
class Posting(BaseModel):
    id: str
    company: str
    title: str
    location: str
    url: str
    source: str
    posted_at: datetime | None
    active: bool
    terms: list[str]
    degrees: list[str]
    raw: str
```

Exposes `normalize(s: str) -> str` and `canonical_id(company, title, location) -> str`.

**Done means:** `pytest` passes on normalization edge cases including empty strings,
unicode, "C++", and "Acme, Inc." vs "acme" collapsing to the same value.

### `sources/base.py`

```python
class Source(Protocol):
    name: str
    def fetch(self) -> list[Posting]: ...
```

Every future adapter implements this. That is the entire interface.

### `sources/simplify.py`

Fetches the listings JSON, maps each entry to a `Posting`, computes canonical IDs,
skips entries missing a URL or company. Also maps `active`, `terms`, and `degrees`
directly from the source entry — all three are present on every observed entry, so
no defensive fallback is needed there, unlike `company`/`url`.

**Done means:** running against a saved fixture file (`tests/fixtures/simplify.json`,
a real response captured once and committed) returns a known non-zero count of
correctly-parsed `Posting` objects, asserted by test.

> This fixture rule is not optional. A scraper that silently returns `[]` passes every
> naive unit test. The test must assert a specific count and spot-check specific fields.

### `store.py`

- `init_db()` — create table if absent, idempotent
- `upsert(postings) -> list[Posting]` — insert new rows, return only the ones that were
  actually new (did not already exist by `id`)
- `get_unalerted() -> list[Posting]`
- `mark_alerted(ids)`

Existing rows are never overwritten. First seen wins.

**Done means:** a test inserts the same batch twice and asserts the second `upsert`
returns an empty list.

### `filters.py`

`is_eligible(posting) -> bool`. v1 rules, in order:

1. **Reject** if `active` is `False`
2. **Reject** unless `TARGET_TERM` appears in `terms`
3. **Reject** if `degrees` is non-empty and does not contain `"Bachelor's"` (covers
   Master's-only and PhD-only listings alike; an empty `degrees` list means no
   restriction and passes through)
4. **Reject** if title matches new-grad/full-time patterns: `new grad`, `new graduate`,
   `university grad`, `entry level`, `full[- ]time` — unless `intern` also appears
5. **Reject** if title matches advanced-degree patterns: `phd`, `ph.d`, `masters only`
6. **Reject** if title matches non-SWE intern patterns: `data scien`, `product manag`,
   `hardware`, `mechanical`, `quant`, `business`, `marketing`, `design`
7. **Accept** if title contains `intern` or `internship` or `co-op` or `coop`
8. Otherwise reject

Case-insensitive. Regex with word boundaries, not substring matching — substring
matching on `intern` will match "International."

Config lives in a `config.py` with a `TARGET_YEAR = 2027`, `TARGET_TERM = f"Summer
{TARGET_YEAR}"` (used by rule 2), and `LOCATIONS: list[str] | None` (None = all,
currently unused by `is_eligible`).

**Done means:** a test table of ~25 real titles with hand-labeled expected outcomes,
including at least 5 tricky negatives ("Software Engineer, New Grad 2027",
"Data Science Intern", "International Software Engineer"). All must pass. Plus a
separate hand-labeled table of `(active, terms, degrees)` combinations covering rules
1-3, drawn from real fixture examples.

### `notify.py`

`send(postings) -> list[str]` — posts to the Discord webhook, returns IDs successfully
sent.

- Batch into groups of 10 per message to avoid rate limits
- Sleep 1s between messages
- On HTTP error, return successfully-sent IDs only; do not raise
- Message format: company, title, location, and the URL as a plain link

**Done means:** a test with a mocked HTTP client asserts correct batching and that a
mid-batch failure still returns the IDs sent before it.

### `run.py`

```
init_db()
new = upsert(source.fetch())
eligible = [p for p in get_unalerted() if is_eligible(p)]
sent = send(eligible)
mark_alerted(sent)
log counts at each stage
```

Ordering matters: `mark_alerted` runs only on confirmed sends, so a crash mid-run
re-alerts nothing already delivered and loses nothing not yet delivered.

## Failure handling

- Source fetch fails → log, exit 0. Next run picks it up. Do not alert on failure in v1.
- Discord fails → those postings stay `alerted_at = NULL` and retry next run.
- Never let a partial failure mark things as alerted.

## Scheduling

GitHub Actions, cron every 30 minutes. The SQLite file is committed back to the repo by
the action, or stored via actions cache — pick one and document it.

Secrets: `DISCORD_WEBHOOK_URL` in repo secrets. Never in code.

> 30 minutes, not 1 minute. The source repo updates in batches; polling faster gains
> nothing real and burns your Actions minutes.

## Build order

Each step ends with a working, committed, tested increment.

1. `schema.py` + tests
2. `store.py` + tests (against in-memory SQLite)
3. `sources/simplify.py` + fixture test
4. `filters.py` + labeled-title test table
5. `notify.py` + mocked test
6. `run.py`, run locally end to end, confirm a real Discord message arrives
7. Deploy to GitHub Actions, confirm two consecutive scheduled runs succeed
8. Let it run 7 days. Watch for duplicates and false positives.

Do not start step N+1 until step N's tests pass.

## Instrumentation (for the writeup)

Log to a `metrics.jsonl` on every run: timestamp, fetched count, new count, eligible
count, alerted count, duration. This is where every number in the eventual writeup
comes from — detection latency, dedupe rate, filter precision. Cheap to add now,
impossible to reconstruct later.

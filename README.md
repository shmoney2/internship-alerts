# internship-alerts

Watches [SimplifyJobs/Summer2027-Internships](https://github.com/SimplifyJobs/Summer2027-Internships)
and [vanshb03/Summer2027-Internships](https://github.com/vanshb03/Summer2027-Internships)
for new SWE internship postings and pings a Discord channel within minutes of a new one
appearing, so you can apply before the flood. It only discovers and tracks postings —
it never submits an application for you.

Runs on a 30-minute GitHub Actions cron. Every posting it's ever seen is tracked in a
committed SQLite file, so it never alerts you twice about the same posting.

## How it decides what to alert on

A posting has to pass all of these to get a Discord alert:

- **New** — not already in the local database (deduped by a hash of company + title +
  location, not the source's own ID, so re-scraped/reformatted postings don't slip
  through as "new")
- **Active** — the source still lists it as open
- **Right term** — `Summer 2027` has to be among the posting's listed terms (configurable,
  see below)
- **Bachelor's-eligible** — if the posting lists specific required degrees at all, one of
  them has to be a Bachelor's (so Master's-only / PhD-only listings get filtered out)
- **Actually an SWE internship by title** — rejects new-grad/full-time postings, PhD/advanced-
  degree-only postings, and non-SWE roles (data science, product, hardware, marketing,
  etc.), then requires the title to actually say intern/internship/co-op/coop

See `SPEC.md` for the exact rules and reasoning if you want the full detail — this is
just the summary.

## Using it yourself

### 1. Set up the environment

```bash
git clone https://github.com/shmoney2/internship-alerts.git
cd internship-alerts
python -m venv .venv

# Windows
.venv\Scripts\python.exe -m pip install -e ".[dev]"
# macOS/Linux
.venv/bin/python -m pip install -e ".[dev]"
```

### 2. Get a Discord webhook URL

In Discord: channel settings → Integrations → Webhooks → New Webhook → copy the URL.

### 3. Configure

Copy `.env.example` to `.env` and fill in your webhook URL:

```
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

`.env` is gitignored — it never gets committed. If you want a different target term or
to restrict by location, edit `src/config.py`:

```python
TARGET_YEAR = 2027          # only postings whose terms include "Summer {TARGET_YEAR}"
LOCATIONS = None            # None = no location filtering (not wired up yet, see SPEC.md)
```

### 4. Run it once locally

```bash
# Windows
.venv\Scripts\python.exe -m src.run
# macOS/Linux
.venv/bin/python -m src.run
```

This fetches the source, updates `postings.db`, sends any newly-eligible alerts to
Discord, and appends a line to `metrics.jsonl`. Safe to run repeatedly — nothing gets
double-alerted.

### 5. Run the tests

```bash
# Windows
.venv\Scripts\python.exe -m pytest
# macOS/Linux
.venv/bin/python -m pytest
```

### 6. Deploy on a schedule (optional)

The repo already includes `.github/workflows/run.yml`, which runs the same thing every
30 minutes on GitHub Actions and commits the updated `postings.db`/`metrics.jsonl` back
to the repo so state survives between runs. If you fork this repo:

1. Add `DISCORD_WEBHOOK_URL` as a repository secret: Settings → Secrets and variables →
   Actions → New repository secret.
2. That's it — the workflow is already set to `on: schedule` plus a manual
   `workflow_dispatch` trigger you can use to test it immediately from the Actions tab
   instead of waiting for the next cron tick.

## Project layout

```
src/
  schema.py      # Posting model, canonical ID / normalization
  sources/
    base.py      # Source protocol -- what any adapter has to implement
    simplify.py  # the SimplifyJobs adapter
    vanshb03.py  # the vanshb03 adapter (Summer-season entries only; see note below)
    composite.py # CompositeSource -- fans fetch() out across all sources,
                 # isolates a single source's failure from the others
  store.py       # SQLite persistence and dedupe
  filters.py     # eligibility rules
  notify.py      # Discord embed formatting + delivery
  run.py         # entrypoint: fetch -> dedupe -> filter -> notify -> mark alerted
  config.py      # TARGET_YEAR / LOCATIONS
```

vanshb03's listings only carry a bare season (`Summer`/`Fall`/`Winter`/`Spring`), not a
year, so `sources/vanshb03.py` only ingests `Summer` entries and maps them to `Summer
2027` -- Fall/Winter/Spring entries are dropped since their year can't be derived from
the data.

`SPEC.md` is the full technical spec (data model, exact filter rules, failure handling,
build order). `AGENTS.md` has the rules for anyone (human or agent) making changes here.

## Status

Deployed to GitHub Actions (step 7 of the build order); waiting to confirm two
consecutive scheduled runs succeed before starting the 7-day observation period
(step 8) that watches for duplicate alerts or false positives.

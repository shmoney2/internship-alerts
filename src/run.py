import json
import logging
import os
import time
from datetime import datetime, timezone

from src import store
from src.filters import is_eligible
from src.notify import send
from src.sources.base import Source
from src.sources.composite import CompositeSource
from src.sources.simplify import SimplifySource
from src.sources.vanshb03 import Vanshb03Source

METRICS_PATH = "metrics.jsonl"

logger = logging.getLogger(__name__)


def main(
    source: Source | None = None,
    metrics_path: str = METRICS_PATH,
    db_path: str = store.DEFAULT_DB_PATH,
) -> dict:
    start = time.monotonic()
    source = source or CompositeSource([SimplifySource(), Vanshb03Source()])

    store.init_db(db_path)

    try:
        fetched = source.fetch()
    except Exception:
        logger.exception("source fetch failed; skipping this run")
        record = _metrics_record(fetched=0, new=0, eligible=0, alerted=0, start=start)
        _append_metrics(record, metrics_path)
        return record

    logger.info("fetched %d postings", len(fetched))

    new = store.upsert(fetched)
    logger.info("%d new postings", len(new))

    eligible = [p for p in store.get_unalerted() if is_eligible(p)]
    logger.info("%d eligible postings", len(eligible))

    sent = send(eligible)
    logger.info("%d alerts sent", len(sent))

    store.mark_alerted(sent)

    record = _metrics_record(
        fetched=len(fetched), new=len(new), eligible=len(eligible), alerted=len(sent), start=start
    )
    _append_metrics(record, metrics_path)
    return record


def _metrics_record(*, fetched: int, new: int, eligible: int, alerted: int, start: float) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "fetched": fetched,
        "new": new,
        "eligible": eligible,
        "alerted": alerted,
        "duration": round(time.monotonic() - start, 3),
    }


def _append_metrics(record: dict, metrics_path: str) -> None:
    with open(metrics_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def load_dotenv(path: str = ".env") -> None:
    """Set env vars from a KEY=VALUE .env file. Never overrides a var that's
    already set, so real secrets (e.g. injected by GitHub Actions) always win
    over the local file. Missing file is a silent no-op."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        return

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_dotenv()
    main()

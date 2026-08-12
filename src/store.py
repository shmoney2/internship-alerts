import json
import sqlite3
from datetime import datetime, timezone

from src.schema import Posting

DEFAULT_DB_PATH = "postings.db"

_conn: sqlite3.Connection | None = None

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS postings (
    id TEXT PRIMARY KEY,
    company TEXT NOT NULL,
    title TEXT NOT NULL,
    location TEXT NOT NULL,
    url TEXT NOT NULL,
    source TEXT NOT NULL,
    posted_at TEXT,
    active INTEGER NOT NULL,
    terms TEXT NOT NULL,
    degrees TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    alerted_at TEXT,
    raw TEXT NOT NULL
)
"""


def init_db(path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    global _conn
    if _conn is not None:
        _conn.close()
    _conn = sqlite3.connect(path)
    _conn.execute(_CREATE_TABLE_SQL)
    _conn.commit()
    return _conn


def _get_conn() -> sqlite3.Connection:
    if _conn is None:
        raise RuntimeError("init_db() must be called before using the store")
    return _conn


def upsert(postings: list[Posting]) -> list[Posting]:
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    new_postings = []
    for posting in postings:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO postings
                (id, company, title, location, url, source, posted_at,
                 active, terms, degrees, first_seen_at, alerted_at, raw)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?)
            """,
            (
                posting.id,
                posting.company,
                posting.title,
                posting.location,
                posting.url,
                posting.source,
                posting.posted_at.isoformat() if posting.posted_at else None,
                posting.active,
                json.dumps(posting.terms),
                json.dumps(posting.degrees),
                now,
                posting.raw,
            ),
        )
        if cursor.rowcount == 1:
            new_postings.append(posting)
    conn.commit()
    return new_postings


def get_unalerted() -> list[Posting]:
    conn = _get_conn()
    rows = conn.execute(
        """
        SELECT id, company, title, location, url, source, posted_at,
               active, terms, degrees, raw
        FROM postings
        WHERE alerted_at IS NULL
        """
    ).fetchall()
    return [_row_to_posting(row) for row in rows]


def mark_alerted(ids: list[str]) -> None:
    if not ids:
        return
    conn = _get_conn()
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE postings SET alerted_at = ? WHERE id = ? AND alerted_at IS NULL",
        [(now, id_) for id_ in ids],
    )
    conn.commit()


def _row_to_posting(row: tuple) -> Posting:
    id_, company, title, location, url, source, posted_at, active, terms, degrees, raw = row
    return Posting(
        id=id_,
        company=company,
        title=title,
        location=location,
        url=url,
        source=source,
        posted_at=datetime.fromisoformat(posted_at) if posted_at else None,
        active=bool(active),
        terms=json.loads(terms),
        degrees=json.loads(degrees),
        raw=raw,
    )

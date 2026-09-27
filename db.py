"""db.py — SQLite persistence: signals, dedup, and the broadcast audit log.

One short-lived connection per call. The MVP is a single-process loop, so
connection pooling would be premature; `check_same_thread=False` is set so the
optional Phase 6b prefetch thread can read safely if we add it.
"""

import hashlib
import json
import sqlite3
import uuid
from typing import Any

import config

SCHEMA_PATH = config.BASE_DIR / "schema.sql"


def _connect() -> sqlite3.Connection:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the schema if absent. Idempotent — safe to call on every start."""
    with open(SCHEMA_PATH, encoding="utf-8") as f:
        ddl = f.read()
    conn = _connect()
    try:
        conn.executescript(ddl)
        conn.commit()
    finally:
        conn.close()


def url_hash(source_url: str) -> str:
    """SHA-256 of the canonicalised URL — the dedup key."""
    return hashlib.sha256(source_url.strip().encode("utf-8")).hexdigest()


def signal_exists(source_url: str) -> bool:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT 1 FROM raw_signals WHERE url_hash = ? LIMIT 1",
            (url_hash(source_url),),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def insert_signal(signal: dict[str, Any]) -> bool:
    """Insert one signal. Returns True if new, False if it was a duplicate.

    Relies on the UNIQUE constraint on url_hash rather than a check-then-insert,
    so concurrent callers can't race a duplicate in.
    """
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO raw_signals
                (id, url_hash, source_url, source_name, title, summary_text)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                url_hash(signal["source_url"]),
                signal["source_url"],
                signal["source_name"],
                signal["title"],
                signal.get("summary"),
            ),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()


def get_unused_signals(limit: int = config.MAX_SIGNALS) -> list[dict[str, Any]]:
    """Newest-first unused signals, capped at `limit`."""
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT id, source_url, source_name, title, summary_text
            FROM raw_signals
            WHERE is_used = 0
            ORDER BY ingested_at DESC, rowid DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def mark_signals_used(ids: list[str]) -> int:
    """Flag signals as aired. Returns the number of rows updated."""
    if not ids:
        return 0
    conn = _connect()
    try:
        placeholders = ",".join("?" * len(ids))
        cur = conn.execute(
            f"UPDATE raw_signals SET is_used = 1 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()


def count_signals(source_name: str | None = None) -> int:
    """Total signals, optionally filtered to one source. Used by smoke tests."""
    conn = _connect()
    try:
        if source_name:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM raw_signals WHERE source_name = ?",
                (source_name,),
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) AS n FROM raw_signals").fetchone()
        return row["n"]
    finally:
        conn.close()


def log_broadcast(
    session_id: str,
    transcript: str,
    cited_urls: list[str],
    llm_model: str,
    audio_duration: float | None = None,
    aired_at: str | None = None,
    tts_engine: str = "edge-tts",
) -> None:
    """Write one audit row per aired show (specs §6)."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO broadcast_audit_log
                (session_id, actual_aired_at, full_script_transcript,
                 cited_source_urls, llm_model, tts_engine, audio_duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                aired_at,
                transcript,
                json.dumps(cited_urls),
                llm_model,
                tts_engine,
                audio_duration,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_audit(session_id: str) -> dict[str, Any] | None:
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM broadcast_audit_log WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def set_aired_at(session_id: str, aired_at: str) -> None:
    """Stamp actual_aired_at once the stream has started."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE broadcast_audit_log SET actual_aired_at = ? WHERE session_id = ?",
            (aired_at, session_id),
        )
        conn.commit()
    finally:
        conn.close()

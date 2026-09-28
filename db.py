"""db.py — Supabase (PostgreSQL) persistence: signals, dedup, and the broadcast audit log.

Uses Supabase PostgREST HTTP API for all database operations, eliminating local
SQLite storage. This makes the app fully stateless and cloud-ready (Render, etc.).
"""

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

import config

# Supabase connection details — loaded from environment or .env
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ntuyvfnuilipninvkqgc.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im50dXl2Zm51aWxpcG5pbnZrcWdjIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc5MDU5MTkxOCwiZXhwIjoyMTA2MTY3OTE4fQ.Ka2bFyjttqUE0BdGyhFULuDyTaZOZAYj2FpqkrKaBxE")


def _headers(*, prefer: str = "") -> dict[str, str]:
    """Standard Supabase PostgREST headers."""
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _request(method: str, table: str, params: str = "", body: Any = None,
             prefer: str = "") -> list[dict] | None:
    """Execute a PostgREST request and return parsed JSON."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += f"?{params}"
    data = json.dumps(body).encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(prefer=prefer), method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            content = resp.read().decode()
            if content:
                return json.loads(content)
            return None
    except urllib.error.HTTPError as e:
        error_body = e.read().decode() if e.fp else ""
        print(f"  [db] PostgREST {method} {table} failed ({e.code}): {error_body[:300]}")
        raise


def init_db() -> None:
    """No-op for Supabase — tables are created via Management API / migrations."""
    pass


def url_hash(source_url: str) -> str:
    """SHA-256 of the canonicalised URL — the dedup key."""
    return hashlib.sha256(source_url.strip().encode("utf-8")).hexdigest()


def signal_exists(source_url: str) -> bool:
    h = url_hash(source_url)
    params = urllib.parse.urlencode({"url_hash": f"eq.{h}", "select": "id", "limit": "1"})
    result = _request("GET", "raw_signals", params=params)
    return bool(result)


def insert_signal(signal: dict[str, Any]) -> bool:
    """Insert one signal. Returns True if new, False if it was a duplicate."""
    row = {
        "id": uuid.uuid4().hex,
        "url_hash": url_hash(signal["source_url"]),
        "source_url": signal["source_url"],
        "source_name": signal["source_name"],
        "title": signal["title"],
        "summary_text": signal.get("summary"),
    }
    try:
        _request("POST", "raw_signals", body=row, prefer="return=minimal")
        return True
    except urllib.error.HTTPError as e:
        if e.code == 409:  # Conflict — duplicate url_hash
            return False
        raise


def get_unused_signals(limit: int = config.MAX_SIGNALS) -> list[dict[str, Any]]:
    """Newest-first unused signals, capped at `limit`."""
    params = urllib.parse.urlencode({
        "is_used": "eq.0",
        "select": "id,source_url,source_name,title,summary_text",
        "order": "ingested_at.desc",
        "limit": str(limit),
    })
    result = _request("GET", "raw_signals", params=params)
    return result or []


def get_recent_signals(limit: int = config.MAX_SIGNALS) -> list[dict[str, Any]]:
    """Newest-first active signals (regardless of is_used) to guarantee 24/7 continuous stream."""
    params = urllib.parse.urlencode({
        "select": "id,source_url,source_name,title,summary_text",
        "order": "ingested_at.desc",
        "limit": str(limit),
    })
    result = _request("GET", "raw_signals", params=params)
    return result or []


def mark_signals_used(ids: list[str]) -> int:
    """Flag signals as aired. Returns the number of rows updated."""
    if not ids:
        return 0
    # PostgREST IN filter: id=in.(val1,val2,...)
    id_list = ",".join(ids)
    params = f"id=in.({id_list})"
    _request("PATCH", "raw_signals", params=params, body={"is_used": 1}, prefer="return=minimal")
    return len(ids)


def count_signals(source_name: str | None = None) -> int:
    """Total signals, optionally filtered to one source."""
    params_dict: dict[str, str] = {"select": "id"}
    if source_name:
        params_dict["source_name"] = f"eq.{source_name}"
    params = urllib.parse.urlencode(params_dict)
    headers = _headers(prefer="count=exact")
    url = f"{SUPABASE_URL}/rest/v1/raw_signals?{params}"
    req = urllib.request.Request(url, headers=headers, method="HEAD")
    try:
        with urllib.request.urlopen(req) as resp:
            content_range = resp.headers.get("Content-Range", "")
            # Format: "0-N/total" or "*/total"
            if "/" in content_range:
                return int(content_range.split("/")[-1])
            return 0
    except Exception:
        return 0


def log_broadcast(
    session_id: str,
    transcript: str,
    cited_urls: list[str],
    llm_model: str,
    audio_duration: float | None = None,
    aired_at: str | None = None,
    tts_engine: str = "edge-tts",
) -> None:
    """Write one audit row per aired show."""
    row = {
        "session_id": session_id,
        "actual_aired_at": aired_at,
        "full_script_transcript": transcript,
        "cited_source_urls": json.dumps(cited_urls),
        "llm_model": llm_model,
        "tts_engine": tts_engine,
        "audio_duration_seconds": audio_duration,
    }
    _request("POST", "broadcast_audit_log", body=row, prefer="return=minimal")


def get_audit(session_id: str) -> dict[str, Any] | None:
    params = urllib.parse.urlencode({"session_id": f"eq.{session_id}", "limit": "1"})
    result = _request("GET", "broadcast_audit_log", params=params)
    return result[0] if result else None


def set_aired_at(session_id: str, aired_at: str) -> None:
    """Stamp actual_aired_at once the stream has started."""
    params = urllib.parse.urlencode({"session_id": f"eq.{session_id}"})
    _request("PATCH", "broadcast_audit_log", params=params,
             body={"actual_aired_at": aired_at}, prefer="return=minimal")

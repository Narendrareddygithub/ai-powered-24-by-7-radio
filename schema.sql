-- schema.sql — 24/7 AI Radio Station (MVP)
-- Applied by db.init_db() on every startup; all statements are idempotent.

CREATE TABLE IF NOT EXISTS raw_signals (
    id            TEXT PRIMARY KEY,             -- uuid4().hex
    url_hash      TEXT NOT NULL UNIQUE,         -- sha256(canonical source_url)
    source_url    TEXT NOT NULL,
    source_name   TEXT NOT NULL,                -- 'hackernews' | 'github_trending'
    title         TEXT NOT NULL,
    summary_text  TEXT,                         -- HN score/comments or repo blurb
    ingested_at   TEXT DEFAULT (datetime('now')),
    is_used       INTEGER DEFAULT 0             -- 1 once included in an aired script
);

CREATE INDEX IF NOT EXISTS idx_raw_signals_unused
    ON raw_signals(is_used) WHERE is_used = 0;

CREATE TABLE IF NOT EXISTS broadcast_audit_log (
    session_id               TEXT PRIMARY KEY,  -- uuid4().hex
    actual_aired_at          TEXT,              -- set when stream starts
    full_script_transcript   TEXT NOT NULL,     -- exact words synthesized
    cited_source_urls        TEXT NOT NULL,     -- JSON array of source URLs
    llm_model                TEXT NOT NULL,
    tts_engine               TEXT DEFAULT 'edge-tts',
    audio_duration_seconds   REAL,
    created_at               TEXT DEFAULT (datetime('now'))
);

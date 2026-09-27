"""ingestion.py — pull fresh signals from the open internet.

Two keyless sources (specs §7.2):

  * Hacker News top stories  — Firebase JSON API
  * GitHub Trending          — unofficial RSS mirror

Each source is wrapped in its own try/except: a dead feed degrades the cycle to
"fewer signals", never to a crashed cycle. Signals are shared as plain dicts
with the shape ``{source_url, source_name, title, summary}``.
"""

import html
import re
from typing import Any

import feedparser
import httpx

import config

HN_TOPSTORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
HN_ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{id}.json"
GITHUB_TRENDING_RSS = (
    "https://mshibanami.github.io/GitHubTrendingRSS/daily/all.xml"
)

TIMEOUT = 15.0
USER_AGENT = "ai-powered-247-radio/0.1 (hackathon MVP)"
SUMMARY_MAX_CHARS = 500

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def clean_text(raw: str | None) -> str:
    """Strip HTML tags/entities and collapse whitespace."""
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return _WS_RE.sub(" ", text).strip()


def fetch_hackernews_top(count: int = config.HN_TOP_COUNT) -> list[dict[str, Any]]:
    """Top `count` HN stories that have an external URL.

    Ask HN / Show HN self-posts carry no `url` and are skipped — the show needs
    linkable sources for the audit log's cited URLs.
    """
    headers = {"User-Agent": USER_AGENT}
    with httpx.Client(timeout=TIMEOUT, headers=headers, follow_redirects=True) as client:
        story_ids = client.get(HN_TOPSTORIES_URL).json()

        signals: list[dict[str, Any]] = []
        for story_id in story_ids[: count * 2]:  # over-fetch; some lack a url
            if len(signals) >= count:
                break
            try:
                item = client.get(HN_ITEM_URL.format(id=story_id)).json()
            except Exception:  # noqa: BLE001 — one bad item shouldn't kill the batch
                continue
            if not item or item.get("type") != "story":
                continue
            url = (item.get("url") or "").strip()
            title = clean_text(item.get("title"))
            if not url or not title:
                continue

            score = item.get("score")
            comments = item.get("descendants", 0)
            signals.append(
                {
                    "source_url": url,
                    "source_name": "hackernews",
                    "title": title,
                    "summary": f"HN score: {score}, comments: {comments}",
                }
            )
        return signals


def fetch_github_trending(limit: int = 20) -> list[dict[str, Any]]:
    """Repos from the GitHub Trending RSS mirror.

    The mirror publishes ~15 entries daily; `limit` is a ceiling, not a promise.
    """
    feed = feedparser.parse(GITHUB_TRENDING_RSS)
    if feed.bozo and not feed.entries:
        raise RuntimeError(f"GitHub Trending feed unparseable: {feed.bozo_exception}")

    signals: list[dict[str, Any]] = []
    for entry in feed.entries[:limit]:
        url = (entry.get("link") or "").strip()
        title = clean_text(entry.get("title"))
        if not url or not title:
            continue
        signals.append(
            {
                "source_url": url,
                "source_name": "github_trending",
                "title": title,
                "summary": clean_text(entry.get("summary"))[:SUMMARY_MAX_CHARS],
            }
        )
    return signals


# (name, fetcher) — also drives the Phase 2 degraded-mode test.
SOURCES: list[tuple[str, Any]] = [
    ("hackernews", fetch_hackernews_top),
    ("github_trending", fetch_github_trending),
]


def ingest_all() -> dict[str, Any]:
    """Fetch every source and persist new signals.

    Returns a summary dict::

        {"fetched": {source: n, ...}, "new": {source: n, ...},
         "errors": {source: msg, ...}, "total_new": n}

    A failing source is recorded in `errors` and skipped; the others still run.
    """
    import db  # local import keeps the module importable without a database

    fetched: dict[str, int] = {}
    new: dict[str, int] = {}
    errors: dict[str, str] = {}

    for name, fetcher in SOURCES:
        try:
            signals = fetcher()
        except Exception as exc:  # noqa: BLE001 — per-source isolation is the point
            errors[name] = f"{type(exc).__name__}: {exc}"
            continue

        fetched[name] = len(signals)
        inserted = 0
        for signal in signals:
            try:
                if db.insert_signal(signal):
                    inserted += 1
            except Exception as exc:  # noqa: BLE001
                errors[name] = f"insert failed: {type(exc).__name__}: {exc}"
        new[name] = inserted

    return {
        "fetched": fetched,
        "new": new,
        "errors": errors,
        "total_new": sum(new.values()),
    }

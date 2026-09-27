# EXECUTION_PLAN.md — Phase-Gated Build (Hackathon Edition)

> Companion to `specs.md`. **Each phase ends with a verification gate — the next phase does not start until the gate passes.** If a gate fails: debug within the phase, or explicitly descope with a note.
>
> Total: ~4.5 hr build + ~30 min buffer. Clock started at Phase 0.

---

## Phase 0 — Environment & Credentials (30 min)

**Build**
1. Create `.venv`, install `requirements.txt`
2. Download portable static FFmpeg (Windows x64) → `tools/ffmpeg/bin/` (config resolves it automatically)
3. Generate `assets/static_visual.jpg` via `tools/make_visual.py`
4. Create `.env` from `.env.example` — user pastes `GROQ_API_KEY` + `YOUTUBE_STREAM_KEY`

**✅ Gate 0**
- [ ] `python --version` → 3.13.x in venv; all deps import
- [ ] `tools/ffmpeg/bin/ffmpeg.exe -version` prints a version line
- [ ] `assets/static_visual.jpg` exists, 1280×720
- [ ] `.env` contains both keys (non-placeholder)
- [ ] **YouTube Studio → Go Live reachable** (user confirms live streaming is enabled — if "enable" pending, start now, it can take up to 24h)

---

## Phase 1 — SQLite Foundation (30 min)

**Build:** `config.py`, `schema.sql`, `db.py` — per specs §6, §7.1, §7.3. Then `smoke_test.py db`.

**✅ Gate 1**
- [ ] `smoke_test.py db` passes: creates `radio.db`, inserts a test signal, reads it back, dedup correctly rejects the same URL, marks used, audit log round-trips
- [ ] `radio.db` shows the expected tables via a quick query

---

## Phase 2 — Signal Ingestion (45 min)

**Build:** `ingestion.py` per specs §7.2 (HN top-20 + GitHub Trending RSS, per-source try/except). Wire into `smoke_test.py ingest`.

**✅ Gate 2**
- [ ] `smoke_test.py ingest` prints fetched counts and writes new rows
- [ ] SQLite contains **≥ 15 total signals** from **both** sources (`hackernews` + `github_trending`)
- [ ] Re-running ingest immediately adds ~0 new rows (dedup works)
- [ ] Single bad feed simulated → other source still ingests (error logged, no crash)

---

## Phase 3 — Script Generation (40 min)

**Build:** `script_gen.py` per specs §7.4 — single Groq call, Nova persona, ~1,500 words. Wire into `smoke_test.py script`.

**✅ Gate 3**
- [ ] `smoke_test.py script` prints the script; word count ≈ 1,200–2,000
- [ ] Script reads like radio (cold open → deep dive → community → recap/teaser), references the actual signals
- [ ] No stage directions / [MUSIC] / timestamps in output
- [ ] (Sanity) cited_urls matches the signals used

---

## Phase 4 — Audio Synthesis (40 min)

**Build:** `audio_synth.py` per specs §7.5 — chunk → edge-tts MP3s → concat → AAC; save `.txt` alongside. Wire into `smoke_test.py audio`.

**✅ Gate 4**
- [ ] `smoke_test.py audio` produces `queue/session_*.aac` + paired `.txt`
- [ ] Audio **plays locally** and sounds natural (user listens to a sample)
- [ ] Duration printed by ffprobe ≈ 8–14 min for ~1,500 words
- [ ] `ffprobe` shows AAC, 128 kbps, 44.1 kHz, stereo
- [ ] Temp chunk files cleaned up

---

## Phase 5 — YouTube Broadcast (45 min)

**Build:** `streamer.py` per specs §7.6 — FFmpeg RTMPS push, Popen list-argv, key check first. Wire into `smoke_test.py full`.

**✅ Gate 5**
- [ ] Stream appears in **YouTube Studio → Stream Health** (ingest bitrate > 0)
- [ ] Preview shows branded visual + audible audio
- [ ] Stream runs **full audio duration** then FFmpeg exits cleanly (returncode 0)
- [ ] After stream end, YouTube still shows the broadcast (same key can rejoin)
- [ ] Wrong-key scenario → clean error, no silent idle (test with dummy key once)

---

## Phase 6 — Autonomous Loop (40 min)

**Build:** `radio.py` + `main.py` per specs §7.7 — the loop with ingest → produce → stream → audit. Include cycle banner logging (cycle #, signals used, script words, audio duration).

**✅ 6a Gate**
- [ ] `python main.py` runs **2 full cycles unattended** (~25 min)
- [ ] Cycle 2 script content **differs** from cycle 1 (fresh stories)
- [ ] `broadcast_audit_log` has 1 row per aired show, transcript + cited URLs
- [ ] YouTube Live playable during both cycles

**Stretch 6b (only if all gates green + time remains):** prefetch next show in a `threading.Thread` during current stream → gapless.

**✅ 6b Gate (stretch)**
- [ ] Gap between show N end and show N+1 start < 10 s in YouTube stream

---

## Phase 7 — Ship It (30 min)

**Build**
1. Update README build-status table (all → ✅)
2. Add demo notes: how to run (`cp .env.example .env`, `python main.py`), stream link
3. Commit + push everything (code, specs, execution plan, updated README) — `.env`/`queue/`/`radio.db` stay ignored

**✅ Gate 7**
- [ ] Repo pushed; README renders with updated status
- [ ] `git status` clean; secrets scan confirms no `.env`/keys committed
- [ ] Final demo: fresh clone → venv → install → `.env` → `python main.py` works (walkthrough documented)

---

## Time Budget Summary

| Phase | Focus | Est. |
|-------|-------|------|
| 0 | Env + credentials + FFmpeg + visual | 30 min |
| 1 | SQLite | 30 min |
| 2 | Ingestion | 45 min |
| 3 | Script gen | 40 min |
| Studio wait | (parallel — YouTube enable pending, if any) | — |
| 4 | TTS → AAC | 40 min  |
| 5 | Stream to YouTube | 45 min |
| 6 | Autonomous loop | 40 min |
| 7 | Ship | 30 min |
| — | Buffer | ~30 min |
| | **Total** | **~4 hr 40 min** |

---

## Failure & Descope Rules

- Gate fails → debug in-phase. If blocked > 20 min, descope and note it in this file.
- Descopes ranked (drop in this order): 6b prefetch → audit-log polish → Pillow visual (reuse a solid-color generated image via FFmpeg) → script `.txt` sidecar.
- **Never drop:** working YouTube stream, fresh content per cycle, loop autonomy.
- If YouTube activation is still pending at Phase 5, we demo via local file playback of the generated shows + full pipeline running, and go live the moment access clears.

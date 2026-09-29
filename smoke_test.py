"""smoke_test.py — phase-by-phase verification runner (no streaming).

Each subcommand is the executable form of a phase gate in EXECUTION_PLAN.md:

    python smoke_test.py db       # Gate 1 — SQLite foundation
    python smoke_test.py ingest   # Gate 2 — signal ingestion
    python smoke_test.py script   # Gate 3 — Groq script generation
    python smoke_test.py audio    # Gate 4 — TTS -> AAC
    python smoke_test.py stream   # Gate 5 — live RTMP push (local MediaMTX by default)
    python smoke_test.py full     # Gates 1-4 end to end, still no streaming
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime, timezone

import audio_synth
import config
import db

PASS = "  [PASS]"
FAIL = "  [FAIL]"


class Checks:
    """Accumulates pass/fail results so one run reports every gate item."""

    def __init__(self) -> None:
        self.failures = 0

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        mark = PASS if ok else FAIL
        line = f"{mark} {label}"
        if detail:
            line += f" — {detail}"
        print(line)
        if not ok:
            self.failures += 1
        return ok


def _sample_signal(n: int) -> dict:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return {
        "source_url": f"https://example.com/article/{ts}/{n}",
        "source_name": "hackernews" if n % 2 == 0 else "github_trending",
        "title": f"Synthetic test signal #{n}",
        "summary": f"Blurb for synthetic signal {n}.",
    }


def smoke_db(c: Checks) -> None:
    """Gate 1 — schema creation, insert, read-back, dedup, mark-used, audit."""
    print("\n=== Gate 1: SQLite foundation ===")

    db.init_db()
    c.check("init_db() creates the database", config.DB_PATH.exists(),
            str(config.DB_PATH))

    samples = [_sample_signal(i) for i in range(1, 6)]
    inserted = [db.insert_signal(s) for s in samples]
    c.check("insert_signal() accepts fresh signals", all(inserted),
            f"{sum(inserted)}/{len(samples)} inserted")

    dupes = [db.insert_signal(s) for s in samples]
    c.check("dedup rejects the same URLs", not any(dupes),
            f"{dupes.count(False)}/{len(dupes)} rejected")

    c.check("signal_exists() finds an inserted URL",
            db.signal_exists(samples[0]["source_url"]))
    c.check("signal_exists() misses an unknown URL",
            not db.signal_exists("https://example.com/never-inserted"))

    unused = db.get_unused_signals(limit=10)
    c.check("get_unused_signals() reads back rows",
            any(s["source_url"] == samples[0]["source_url"] for s in unused),
            f"{len(unused)} unused returned")

    ids = [s["id"] for s in unused[:2]]
    updated = db.mark_signals_used(ids)
    c.check("mark_signals_used() flags rows", updated == len(ids),
            f"{updated} rows updated")

    remaining = {s["id"] for s in db.get_unused_signals(limit=10)}
    c.check("marked signals drop out of the unused set",
            not (set(ids) & remaining))

    session_id = "smoke-" + datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    transcript = "This is a synthetic transcript for the audit round-trip test."
    cited = [samples[0]["source_url"], samples[1]["source_url"]]
    db.log_broadcast(
        session_id=session_id,
        transcript=transcript,
        cited_urls=cited,
        llm_model="smoke-test-model",
        audio_duration=123.4,
    )
    row = db.get_audit(session_id)
    c.check("audit log round-trips", row is not None and
            row["full_script_transcript"] == transcript and
            row["audio_duration_seconds"] == 123.4,
            f"session_id={session_id}")

    db.set_aired_at(session_id, datetime.now(timezone.utc).isoformat())
    row = db.get_audit(session_id)
    c.check("set_aired_at() stamps the air time",
            row is not None and row["actual_aired_at"] is not None)

    total = db.count_signals()
    c.check("raw_signals contains the expected rows", total >= 5,
            f"{total} total signals")


def smoke_ingest(c: Checks) -> None:
    """Gate 2 — both sources ingest, dedup holds, one dead feed is survivable."""
    import ingestion

    print("\n=== Gate 2: signal ingestion ===")

    db.init_db()
    before = db.count_signals()

    result = ingestion.ingest_all()
    hn = result["new"].get("hackernews", 0)
    gh = result["new"].get("github_trending", 0)

    print(f"  fetched: {result['fetched']}")
    print(f"  new:     {result['new']}")
    if result["errors"]:
        print(f"  errors:  {result['errors']}")

    c.check("no source errored", not result["errors"],
            str(result["errors"]) if result["errors"] else "both sources healthy")
    c.check("hackernews produced signals", hn > 0, f"{hn} new")
    c.check("github_trending produced signals", gh > 0, f"{gh} new")

    total_hn = db.count_signals("hackernews")
    total_gh = db.count_signals("github_trending")
    c.check("both sources present in the database",
            total_hn > 0 and total_gh > 0,
            f"hackernews={total_hn}, github_trending={total_gh}")
    c.check("at least 15 total signals", db.count_signals() >= 15,
            f"{db.count_signals()} total")

    # Re-run: everything is already known, so nothing new should land.
    again = ingestion.ingest_all()
    c.check("re-ingest adds ~0 new rows (dedup works)",
            again["total_new"] == 0,
            f"{again['total_new']} new on second pass")
    c.check("row count stable across re-ingest",
            db.count_signals() ==
            before + result["total_new"],
            f"{db.count_signals()} rows")

    # Degraded mode: break one source, confirm the other still ingests.
    original = ingestion.SOURCES
    def _boom() -> list:
        raise RuntimeError("simulated feed outage")

    try:
        ingestion.SOURCES = [("dead_feed", _boom)] + [
            (n, f) for n, f in original if n == "hackernews"
        ]
        degraded = ingestion.ingest_all()
        c.check("dead feed is isolated (error recorded, no crash)",
                "dead_feed" in degraded["errors"])
        c.check("healthy source still runs alongside a dead one",
                degraded["fetched"].get("hackernews", 0) > 0,
                f"hackernews fetched {degraded['fetched'].get('hackernews', 0)}")
    finally:
        ingestion.SOURCES = original


def smoke_script(c: Checks) -> None:
    """Gate 3 — the LLM writes a radio-length script with no TTS-hostile cues."""
    import re

    import script_gen

    print("\n=== Gate 3: script generation ===")

    db.init_db()
    signals = db.get_unused_signals(limit=config.MAX_SIGNALS)
    print(f"  signals available: {len(signals)}")
    if not c.check("enough signals to write a show",
                   len(signals) >= config.MIN_SIGNALS,
                   f"{len(signals)} (min {config.MIN_SIGNALS})"):
        return

    print(f"  calling {config.GROQ_MODEL} ...")
    script, cited = script_gen.generate_show_script(signals)

    if not c.check("script generated", script is not None):
        return

    words = script_gen.word_count(script)
    c.check("word count in the 1,200-2,000 range",
            1200 <= words <= 2000, f"{words} words")
    c.check("cited URLs match the signals used",
            cited == [s["source_url"] for s in signals],
            f"{len(cited)} cited")

    # Anything bracketed or asterisked gets read aloud literally by TTS.
    cues = re.findall(r"\[[^\]]{0,40}\]|\([^)]{0,40}\)|\*[^*]{0,40}\*", script)
    noisy = [m for m in cues if not re.fullmatch(r"\(\d{4}\)", m)]
    c.check("no stage directions / sound cues / markdown",
            not noisy, f"{len(noisy)} found: {noisy[:3]}" if noisy else "clean")

    c.check("no markdown headings or bullets",
            not re.search(r"^\s*(#|\*|-|\d+\.)\s", script, flags=re.MULTILINE))

    lower = script.lower()
    c.check("host does not out itself as an AI",
            not re.search(r"\b(as an ai|i am an ai|language model|i'm an ai)\b", lower))

    c.check("reads like radio prose (multiple paragraphs)",
            len([p for p in script.split("\n\n") if p.strip()]) >= 3,
            f"{len([p for p in script.split(chr(10)+chr(10)) if p.strip()])} paragraphs")

    print("\n--- script preview (first 700 chars) ---")
    print(script[:700])
    print("--- end preview ---\n")
    print(f"  full script length: {len(script)} chars, {words} words")


def smoke_audio(c: Checks) -> None:
    """Gate 4 — script to AAC: chunking, encoding params, duration, cleanup."""
    import subprocess

    import audio_synth
    import script_gen

    print("\n=== Gate 4: audio synthesis ===")

    # Chunker correctness first — cheap, and it gates everything downstream.
    long_para = "This is a sentence. " * 800          # ~16k chars, no blank lines
    pieces = audio_synth.chunk_script(long_para, max_chars=8000)
    c.check("chunker splits an oversized paragraph",
            len(pieces) > 1 and all(len(p) <= 8000 for p in pieces),
            f"{len(pieces)} pieces, max {max((len(p) for p in pieces), default=0)} chars")

    db.init_db()
    signals = db.get_unused_signals(limit=config.MAX_SIGNALS)
    script, _ = script_gen.generate_show_script(signals)
    if not c.check("script available to synthesize", script is not None):
        return

    print(f"  synthesizing {script_gen.word_count(script)} words ...")
    aac_path, duration = audio_synth.synthesize_audio(script)

    if not c.check("AAC produced", aac_path is not None and aac_path.exists(),
                   str(aac_path)):
        return

    txt_path = aac_path.with_suffix(".txt")
    c.check("script .txt sidecar written", txt_path.exists(), txt_path.name)
    c.check("sidecar matches the synthesized words",
            txt_path.read_text(encoding="utf-8") == script)

    c.check("duration in the 8-14 min range",
            8 * 60 <= duration <= 14 * 60, f"{duration / 60:.1f} min")

    probe = subprocess.run(
        [config.FFPROBE, "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,bit_rate,sample_rate,channels",
         "-of", "default=noprint_wrappers=1", str(aac_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    props = dict(
        line.split("=", 1) for line in probe.stdout.strip().splitlines() if "=" in line
    )
    print(f"  stream properties: {props}")
    c.check("codec is AAC", props.get("codec_name") == "aac")
    c.check("stereo", props.get("channels") == "2")
    c.check("44.1 kHz", props.get("sample_rate") == "44100")

    leftovers = list(config.QUEUE_DIR.glob("chunk_*")) + list(config.QUEUE_DIR.glob("*.mp3"))
    c.check("temp chunk files cleaned up", not leftovers,
            f"{len(leftovers)} leftover" if leftovers else "none")

    print(f"\n  LISTEN TO THIS: {aac_path}")


def smoke_stream(c: Checks) -> None:
    """Gate 5 — FFmpeg pushes a real show to the configured RTMP target.

    Uses the newest queued AAC, or synthesizes one if the queue is empty.
    With the default local target this is fully self-contained: MediaMTX is
    started, the show streams, and http://localhost:8888/radio plays it.
    """
    import streamer

    print("\n=== Gate 5: live broadcast ===")

    if not c.check("static visual present", config.STATIC_VISUAL.exists(),
                   str(config.STATIC_VISUAL)):
        return

    # Find the newest finished show, or make one so this gate is self-sufficient.
    aac_files = sorted(
        (p for p in config.QUEUE_DIR.glob("session_*.aac") if p.exists()),
        key=lambda p: p.name,
    )
    if aac_files:
        aac_path = aac_files[-1]
        mp4_path = aac_path.with_suffix(".mp4")
        if not mp4_path.exists():
            print(f"  pre-encoding show MP4: {aac_path.name}...")
            mp4_path, duration = audio_synth.pre_encode_show(aac_path)
        else:
            duration = audio_synth.probe_duration(aac_path)
        print(f"  using queued show MP4: {mp4_path.name} ({duration / 60:.1f} min)")
    else:
        import script_gen
        print("  queue empty — synthesizing a fresh show first")
        signals = db.get_unused_signals(limit=config.MAX_SIGNALS)
        script, _ = script_gen.generate_show_script(signals)
        if not c.check("script available", script is not None):
            return
        aac_path, duration = audio_synth.synthesize_audio(script)
        if not c.check("show synthesized", aac_path is not None):
            return
        mp4_path, duration = audio_synth.pre_encode_show(aac_path)
        if not c.check("show pre-encoded", mp4_path is not None and mp4_path.exists()):
            return

    server_proc = None
    if "localhost" in config.STREAM_URL or "127.0.0.1" in config.STREAM_URL:
        server_proc = streamer.start_local_server()
        if not c.check("MediaMTX local server started", server_proc is not None):
            return
        c.check("ingest port 1935 is listening", _port_open(1935))
        c.check("HLS port 8888 is listening", _port_open(8888))

    key = config.STREAM_KEY or "radio"
    proc = streamer.stream_show(mp4_path, duration)


    # Let the push run long enough to prove real bytes flow, then stop it —
    # nobody sits through a full 12-min show during a gate run.
    print("  pushing live for 15s ...")
    time.sleep(15)
    alive = proc.poll() is None
    c.check("stream process still alive after 15s of pushing", alive,
            f"rc={proc.returncode}" if not alive else "no early exit")

    if alive:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    c.check("stream process shut down cleanly",
            proc.returncode is not None)

    if server_proc:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()

    if alive:
        print("\n  A 15-second live test just ran. If STREAM_URL is the local")
        print("  target, open http://localhost:8888/radio while a show is")
        print("  streaming to watch it live.")


def _port_open(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex((host, port)) == 0


def smoke_full(c: Checks) -> None:
    """Gates 1-4: full pipeline end-to-end (ingest -> script -> audio -> db log), no streaming."""
    import audio_synth
    import script_gen
    import ingestion

    print("\n=== Gate 6: full pipeline end-to-end ===")

    db.init_db()
    ingest_res = ingestion.ingest_all()
    c.check("ingestion ran cleanly", not ingest_res["errors"])

    signals = db.get_unused_signals(limit=config.MAX_SIGNALS)
    if not c.check("signals available for show generation", len(signals) >= config.MIN_SIGNALS, f"{len(signals)} signals"):
        return

    print(f"  generating script with {config.GROQ_MODEL} ...")
    script, cited = script_gen.generate_show_script(signals)
    if not c.check("script generated", script is not None):
        return

    words = script_gen.word_count(script)
    c.check("script word count valid", 1200 <= words <= 2000, f"{words} words")

    print(f"  synthesizing audio with edge-tts ...")
    aac_path, duration = audio_synth.synthesize_audio(script)
    if not c.check("audio synthesized", aac_path is not None and aac_path.exists()):
        return

    session_id = f"smoke_full_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    db.log_broadcast(
        session_id=session_id,
        transcript=script,
        cited_urls=cited,
        llm_model=config.GROQ_MODEL,
        audio_duration=duration,
        tts_engine=f"edge-tts ({config.TTS_VOICE})"
    )

    signal_ids = [s["id"] for s in signals]
    updated = db.mark_signals_used(signal_ids)
    c.check("signals marked used in database", updated == len(signal_ids))

    audit = db.get_audit(session_id)
    c.check("broadcast audit row logged", audit is not None and audit["audio_duration_seconds"] == duration)

    print(f"  Full pipeline verified successfully! Audio: {aac_path.name} ({duration/60:.1f} min)")


COMMANDS = {
    "db": smoke_db,
    "ingest": smoke_ingest,
    "script": smoke_script,
    "audio": smoke_audio,
    "stream": smoke_stream,
    "full": smoke_full,
}


def main() -> int:
    # LLM output contains smart quotes, non-breaking hyphens, and em dashes;
    # Windows consoles default to cp1252 and raise on them.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    args = parser.parse_args()

    print(f"smoke_test: {args.command}")

    checks = Checks()
    try:
        COMMANDS[args.command](checks)
    except Exception as exc:  # noqa: BLE001 — a crashed smoke test is a failed gate
        print(f"{FAIL} {args.command} raised: {type(exc).__name__}: {exc}")
        return 1

    print()
    if checks.failures:
        print(f"RESULT: FAIL — {checks.failures} check(s) failed")
        return 1
    print("RESULT: PASS — gate green")
    return 0


if __name__ == "__main__":
    sys.exit(main())

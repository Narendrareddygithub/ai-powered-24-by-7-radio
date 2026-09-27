"""radio.py — autonomous station orchestrator (specs §7.7, Phase 6).

Coordinates the infinite live radio loop:
1. INGEST  : Fetch fresh signals from HN API + GitHub Trending RSS.
2. PRODUCE : Groq LLM writes a 100% fresh script -> edge-tts renders AAC audio.
3. LOG     : Record transcript & cited URLs in SQLite audit log; mark signals as used.
4. STREAM  : Push video + audio live to Twitch/YouTube via FFmpeg RTMPS.
5. REPEAT  : Once audio finishes, immediately loop to step 1 with new signals.
"""

import time
import uuid
from datetime import datetime, timezone

import audio_synth
import config
import db
import ingestion
import script_gen
import streamer


def run_cycle(cycle_num: int) -> bool:
    """Execute a single end-to-end signal-to-air cycle.

    Returns True if a show was produced and aired, False if skipped (e.g. starved).
    """
    print(f"\n==================================================")
    print(f" 🎙️  CYCLE #{cycle_num} STARTING — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print(f"==================================================")

    # 1. INGEST fresh signals
    print("\n[Step 1/4] Ingesting fresh live signals...")
    ingest_result = ingestion.ingest_all()
    print(f"  Fetched: {ingest_result['fetched']}")
    print(f"  New added: {ingest_result['new']} (total new: {ingest_result['total_new']})")
    if ingest_result['errors']:
        print(f"  Feed errors: {ingest_result['errors']}")

    # 2. FETCH UNUSED SIGNALS
    signals = db.get_unused_signals(limit=config.MAX_SIGNALS)
    print(f"\n[Step 2/4] Pulling un-aired signals from database ({len(signals)} available)...")

    if len(signals) < config.MIN_SIGNALS:
        print(f"  ⚠️ Warning: Only {len(signals)} un-aired signals available (minimum is {config.MIN_SIGNALS}).")
        print("  Skipping production for this cycle; sleeping 60 seconds before re-ingesting...")
        time.sleep(60)
        return False

    # 3. PRODUCE SHOW (LLM Script + TTS Audio)
    print(f"\n[Step 3/4] Producing show with Groq ({config.GROQ_MODEL}) & edge-tts...")
    script, cited_urls = script_gen.generate_show_script(signals)
    if not script:
        print("  ❌ LLM script generation failed! Sleeping 60s before retrying...")
        time.sleep(60)
        return False

    words = script_gen.word_count(script)
    print(f"  ✍️ Script generated: {words} words, citing {len(cited_urls)} source URLs.")

    aac_path, duration = audio_synth.synthesize_audio(script)
    if not aac_path or not aac_path.exists():
        print("  ❌ Audio synthesis failed! Sleeping 60s before retrying...")
        time.sleep(60)
        return False

    mins = duration / 60.0
    print(f"  🔊 Audio synthesized: {aac_path.name} ({mins:.1f} minutes).")

    # LOG AUDIT & MARK SIGNALS USED
    session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    db.log_broadcast(
        session_id=session_id,
        transcript=script,
        cited_urls=cited_urls,
        llm_model=config.GROQ_MODEL,
        audio_duration=duration,
        tts_engine=f"edge-tts ({config.TTS_VOICE})"
    )

    signal_ids = [s["id"] for s in signals]
    db.mark_signals_used(signal_ids)
    print(f"  📝 Session {session_id} logged to broadcast_audit_log; {len(signal_ids)} signals marked as used.")

    # 4. STREAM LIVE TO PLATFORM
    air_time = datetime.now(timezone.utc).isoformat()
    db.set_aired_at(session_id, air_time)

    print(f"\n[Step 4/4] 🔴 BROADCASTING LIVE to {config.STREAM_URL} ...")
    print(f"  Show will play for full audio length ({mins:.1f} min).")

    proc = streamer.stream_show(config.STATIC_VISUAL, aac_path, duration)
    completed = streamer.wait_for_stream(proc, duration)

    if completed:
        print(f"\n✅ CYCLE #{cycle_num} COMPLETED SUCCESSFULLY! Stream ran for full {mins:.1f} minutes.")
    else:
        print(f"\n⚠️ CYCLE #{cycle_num} ENDED EARLY (rc={proc.returncode}). Moving to next cycle...")

    return True


def run_radio_loop():
    """Run the 24/7 autonomous radio station loop forever."""
    db.init_db()
    config.require_credentials("GROQ_API_KEY", "STREAM_KEY")

    print("\n" + "=" * 60)
    print(" 📻 AI-POWERED 24/7 RADIO STATION — AUTONOMOUS LIVE BROADCAST")
    print(f" Target: {config.STREAM_URL}")
    print(f" Model : {config.GROQ_MODEL}")
    print(f" Voice : {config.TTS_VOICE}")
    print("=" * 60 + "\n")

    cycle_num = 1
    while True:
        try:
            run_cycle(cycle_num)
            cycle_num += 1
        except KeyboardInterrupt:
            print("\n👋 Station shut down by user.")
            break
        except Exception as exc:
            print(f"\n❌ Unhandled cycle error: {type(exc).__name__}: {exc}")
            print("Restarting loop in 30 seconds...")
            time.sleep(30)

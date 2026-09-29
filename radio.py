"""radio.py — autonomous station orchestrator with lookahead prefetching (Phase 6b).

Architecture:
- Background Producer Thread: Maintains pre-rendered shows in SHOW_QUEUE while
  the current show is streaming live on air.
- Streamer Loop: Pops pre-rendered shows from SHOW_QUEUE and streams them instantly.
- Transition gap between shows: < 2 seconds (100% gapless continuous live broadcast).
"""

import queue
import threading
import time
import uuid
from datetime import datetime, timezone

import audio_synth
import config
import db
import ingestion
import script_gen
import streamer

# Thread-safe queue holding pre-produced show dicts
SHOW_QUEUE: queue.Queue = queue.Queue(maxsize=2)
_PRODUCER_RUNNING = True


def _produce_one_show(show_index: int) -> dict | None:
    """Produce a single show (Ingest -> Groq Script -> edge-tts AAC) without streaming."""
    print(f"\n[Producer Thread] 🎛️ Preparing Show #{show_index} in background...")

    # 1. Ingest fresh signals
    ingest_res = ingestion.ingest_all()
    print(f"  [Producer] Ingested: {ingest_res['fetched']} (new: {ingest_res['new']})")

    # 2. Fetch signals (unused first, fallback to recent top stories)
    signals = db.get_unused_signals(limit=config.MAX_SIGNALS)
    if len(signals) < config.MIN_SIGNALS:
        print(f"  [Producer] 📡 Falling back to active top stories for 24/7 continuous stream...")
        signals = db.get_recent_signals(limit=config.MAX_SIGNALS)

    if not signals:
        print("  [Producer] ⚠️ No signals available in database.")
        return None

    # 3. Generate Groq LLM script
    print(f"  [Producer] ✍️ Writing script with Groq ({config.GROQ_MODEL})...")
    script, cited_urls = script_gen.generate_show_script(signals)
    if not script:
        print("  [Producer] ❌ Script generation failed.")
        return None

    words = script_gen.word_count(script)

    # 4. Synthesize AAC audio
    print(f"  [Producer] 🔊 Synthesizing TTS audio ({words} words)...")
    aac_path, duration = audio_synth.synthesize_audio(script)
    if not aac_path or not aac_path.exists():
        print("  [Producer] ❌ Audio synthesis failed.")
        return None

    # 5. Pre-encode broadcast FLV (visual + AAC audio -> broadcast-ready FLV)
    print(f"  [Producer] 🎬 Pre-encoding broadcast FLV...")
    flv_path, duration = audio_synth.pre_encode_show(aac_path)
    if not flv_path or not flv_path.exists():
        print("  [Producer] ❌ Pre-encoding show failed.")
        return None

    session_id = f"session_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

    # Audit log & mark signals used
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

    mins = duration / 60.0
    print(f"  [Producer] ✅ Show #{show_index} pre-encoded & ready: {flv_path.name} ({mins:.1f} min, {words} words).")

    return {
        "session_id": session_id,
        "flv_path": flv_path,
        "aac_path": aac_path,
        "duration": duration,
        "script": script,
        "cited_urls": cited_urls,
        "show_index": show_index,
    }




def _producer_loop():
    """Background worker thread that keeps SHOW_QUEUE filled with pre-rendered shows."""
    show_counter = 1
    while _PRODUCER_RUNNING:
        try:
            if SHOW_QUEUE.qsize() < 1:
                show = _produce_one_show(show_counter)
                if show:
                    SHOW_QUEUE.put(show)
                    show_counter += 1
                else:
                    time.sleep(30)
            else:
                time.sleep(5)
        except Exception as exc:
            print(f"  [Producer Thread] ⚠️ Production error: {type(exc).__name__}: {exc}")
            time.sleep(15)


def run_radio_loop():
    """Main broadcast loop: streams pre-rendered shows from queue for gapless 24/7 streaming."""
    import sys
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    db.init_db()
    config.require_credentials("GROQ_API_KEY", "STREAM_KEY")

    print("\n" + "=" * 60)
    print(" 📻 AI-POWERED 24/7 RADIO STATION — GAPLESS LIVE BROADCAST")
    print(f" Target: {config.STREAM_URL}")
    print(f" Model : {config.GROQ_MODEL}")
    print(f" Voice : {config.TTS_VOICE}")
    print(" Mode  : Real-Time Prefetching (0-second gap between shows)")
    print("=" * 60 + "\n")

    # Start background producer thread
    producer_thread = threading.Thread(target=_producer_loop, daemon=True)
    producer_thread.start()

    cycle_num = 1
    while True:
        try:
            print(f"\n==================================================")
            print(f" 🎙️  CYCLE #{cycle_num} AIRING — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
            print(f"==================================================")

            print("  ⌛ Waiting for next pre-rendered show from queue...")
            show = SHOW_QUEUE.get()  # Blocks if queue empty until show ready

            session_id = show["session_id"]
            flv_path = show.get("flv_path", show.get("mp4_path", show["aac_path"]))
            duration = show["duration"]
            mins = duration / 60.0

            air_time = datetime.now(timezone.utc).isoformat()
            db.set_aired_at(session_id, air_time)

            print(f"\n🔴 BROADCASTING LIVE to {config.STREAM_URL} ...")
            print(f"  Playing show #{show['show_index']} ({flv_path.name}, {mins:.1f} min)...")

            proc = streamer.stream_show(flv_path, duration)
            completed = streamer.wait_for_stream(proc, duration)


            if completed:
                print(f"✅ CYCLE #{cycle_num} FINISHED! Immediately starting next show from queue...")
            else:
                print(f"⚠️ CYCLE #{cycle_num} ended early (rc={proc.returncode}). Starting next show...")

            cycle_num += 1

        except KeyboardInterrupt:
            print("\n👋 Station shut down by user.")
            break
        except Exception as exc:
            print(f"\n❌ Unhandled stream loop error: {type(exc).__name__}: {exc}")
            time.sleep(10)

# 🎙️ AI-Powered 24/7 Radio

> **An autonomous AI radio DJ that scrapes the open internet, writes its own commentary, and streams to YouTube Live — continuously, with zero humans in the loop.**

<p>
  <img alt="Python"      src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img alt="Groq"        src="https://img.shields.io/badge/LLM-Groq-F55036?style=for-the-badge">
  <img alt="FFmpeg"      src="https://img.shields.io/badge/Streaming-FFmpeg-007808?style=for-the-badge&logo=ffmpeg&logoColor=white">
  <img alt="Twitch"      src="https://img.shields.io/badge/Live-youtube.com-9146FF?style=for-the-badge&logo=youtube&logoColor=red">
  <img alt="Built in Public"   src="https://img.shields.io/badge/Built%20in-Public-FFB000?style=for-the-badge">
</p>

> 🔴 **LIVE DEMO STREAM**: Watch the station broadcasting live on YouTube at **[AI-Powered 24-by-7 Radio](https://www.youtube.com/@AI-powered24-by-7radio)**!

---

## 🎥 Project Explanation

<video src="assets/demo_video.mp4" controls width="100%"></video>


https://github.com/user-attachments/assets/825ed2d6-c8db-46c4-a9e3-b432401e8e05


> 🎬 *Full 7.8-minute walkthrough video explaining the 24/7 AI Radio architecture, live ingestion, LLM script generation, TTS audio synthesis, and real-time RTMP streaming.*
## Live Streaming in YouTube 

Click Here :- **[AI-Powered 24-by-7 Radio](https://www.youtube.com/watch?v=dgMCfWt49eo)** <br> <br>
---

## ⚡ Quickstart — Run the Station

1. **Clone & Setup Environment**:
   ```bash
   git clone https://github.com/Narendrareddygithub/ai-powered-24-by-7-radio.git
   cd ai-powered-24-by-7-radio
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Credentials**:
   ```bash
   cp .env.example .env
   # Edit .env with your GROQ_API_KEY and STREAM_KEY (Twitch / YouTube)
   ```

3. **Launch Autonomous 24/7 Station**:
   ```bash
   python main.py
   ```

## 💡 The Big Idea

| | |
|---|---|
| 🛰️ **It listens** | Continuously ingests breaking signals from Hacker News and GitHub Trending. |
| 🧠 **It thinks** | An LLM writes original editorial commentary — never reads articles verbatim. |
| 📺 **It speaks** | Neural TTS voices it as a radio host, and FFmpeg broadcasts it live to YouTube. |

> [!IMPORTANT]
> **There is no human in the loop.** No playlists. No pre-recorded shows. Every segment that goes on air is synthesized minutes before broadcast, from signals that were published hours earlier.

---

## 🏗️ How It Works — End to End

```mermaid
flowchart LR
    subgraph INGEST["🛰️  INGEST"]
        direction TB
        A1["Hacker News API<br/><i>top stories</i>"]
        A2["GitHub Trending RSS<br/><i>daily repos</i>"]
        A3["SHA-256 URL Hash<br/><i>dedup — skip what we've seen</i>"]
        A4[("SQLite<br/><b>raw_signals</b>")]
        A1 --> A3
        A2 --> A3
        A3 --> A4
    end

    subgraph PRODUCE["🎛️  PRODUCE"]
        direction TB
        B1["Fresh Signals<br/><i>never broadcast</i>"]
        B2["Groq LLM<br/><b>Nova</b> persona writes the script"]
        B3["edge-tts<br/><i>neural voice → AAC</i>"]
        B1 --> B2 --> B3
    end

    subgraph BROADCAST["📺  BROADCAST"]
        direction TB
        C1["FFmpeg<br/>static visual + audio"]
        C2["RTMPS :443"]
        C3["▶️ YouTube Live"]
        C1 --> C2 --> C3
    end

    A4 --> B1
    B3 --> C1
    C3 -. "audio ends → pull FRESH signals" .-> A4

    style INGEST    fill:#0d2033,stroke:#2f81f7,stroke-width:2px,color:#fff
    style PRODUCE   fill:#2b1a33,stroke:#a371f7,stroke-width:2px,color:#fff
    style BROADCAST fill:#331a1a,stroke:#f85149,stroke-width:2px,color:#fff
```

---

## 🔁 The Signal-to-Air Cycle

Each loop is finite — the stream ends when the audio ends, then the whole cycle starts over with brand-new content.

```mermaid
flowchart LR
    S1["🛰️ Pull<br/>signals"] --> S2["🧹 Dedup<br/>vs SQLite"]
    S2 --> S3["✍️ LLM writes<br/>show script"]
    S3 --> S4["🔊 TTS renders<br/>audio"]
    S4 --> S5["📺 Stream to<br/>YouTube Live"]
    S5 --> S6["📼 Log script<br/>+ sources"]
    S6 -. "next cycle — fresh stories" .-> S1

    style S1 fill:#0d2033,stroke:#2f81f7,color:#fff
    style S3 fill:#2b1a33,stroke:#a371f7,color:#fff
    style S5 fill:#331a1a,stroke:#f85149,color:#fff
    style S6 fill:#1a2b1a,stroke:#3fb950,color:#fff
```

---

## 🧰 Tech Stack

| Layer | Tool | Why this one |
|:------|:-----|:-------------|
| 🛰️ **Ingestion** | `httpx` + `feedparser` | Pulls HN's JSON API and GitHub's RSS directly — no keys, no headless browser |
| 🧹 **Dedup** | SHA-256 URL hashing | Identical story from two outlets = one broadcast |
| 🗄️ **State** | SQLite (stdlib) | Zero setup, single file, survives restarts |
| 🧠 **Script** | Groq — `llama-3.3-70b-versatile` | Free tier, no credit card, OpenAI-compatible |
| 🔊 **Voice** | edge-tts | Keyless neural TTS, no character caps |
| 🎬 **Mux** | FFmpeg | Loop a still image, mux the AAC, push RTMPS |
| 📺 **Delivery** | YouTube Live (RTMPS :443) | Free global CDN — the station *is* the channel |

---

## ✅ Build Status

> Built in public at a hackathon. This table is the honest current state.

| Component | Status |
|:----------|:-------|
| 📄 Architecture & scope defined | ✅ Done |
| 🎨 Visual README + public repo | ✅ Done |
| 🛰️ Signal ingestion (HN + GitHub) | ✅ Done |
| 🧹 SHA-256 deduplication | ✅ Done |
| 🧠 LLM script generation (Groq) | ✅ Done |
| 🔊 TTS + AAC rendering | ✅ Done |
| 📺 Live broadcast (Twitch / YouTube RTMP) | ✅ Done |
| 🔁 Autonomous 24/7 loop | ✅ Done |

---

## 🗺️ Roadmap

```mermaid
timeline
    title From today's proof of concept to a real station
    section MVP — today
        Local proof of concept : Ingest HN + GitHub
                                : LLM writes the script
                                : TTS renders audio
                                : Live stream to YouTube
    section V2 — expand
        Cloud hosting : Runs without my laptop
        More shows : 4 rotating formats across the day
        Story clustering : One story, many sources, one segment
        Reliability : Multi-provider LLM failover
    section V3 — scale
        Always-on ops : Crash recovery and rolling queue
        Richer audio : Music bed and ducking
        Real monitoring : Dashboard and public metrics
```

---

## 🤝 Built in Public

Every step of this build lands in this repo — commits, docs, dead ends included.

⭐ **Star the repo** if you want to watch an AI learn to run a radio station.

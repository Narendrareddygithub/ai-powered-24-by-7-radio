Build an ai agent that scrapes your social media account and gives you Voice notes updates. In your account/telegram/whatsapp or email.(Pick the easiest one first.)

Get user goal of using that platform 

Example :- Media :- LinkedIn   
                  Goal :-  Primary :- Job/Internship opportunities  
                               Secondary :- Professional connections/network

1.User should connect their Social media (linkedin) account to this agent .  
2\. Describe the goal in plain English (Both primary \* & secondary(optional)).  
3\. Cron job (Hourly/Everyday/Weekly/Monthly)  
4.Connect Gateway (telegram/whatsapp or email)  
5.Get Voice\&Text updates.

Transformed [Spec.md](http://Spec.md) file

\=============================  
Below is the complete specs.md specification document capturing every architectural constraint, fallback strategy, and infrastructure decision finalized for your 24/7 AI Radio system.

# specs.md **— 24/7 Autonomous AI Radio & Newsroom**

## **1\. Project Overview & Core Constraints**

An autonomous, real-time, audio-first AI newsroom that continuously monitors open internet signals, deduplicates and verifies breaking developments, synthesizes engaging single-host radio commentary, and broadcasts 24/7 to YouTube Live.

### **Hard Constraints**

* **\$0 Cost & Zero Credit Card Required:** Every cloud host, database, LLM provider, and TTS engine must run strictly on free tiers that do not require payment card verification.  
*   
* **100% Cloud-Native Execution:** No reliance on local machine uptime.  
*   
* **Zero Headless Browsers:** No Puppeteer, Playwright, or headless Chrome instances (\<50 MB RAM ingestion footprint).  
*   
* **Genuine 24/7 Content (No Show Looping):** Every 30-minute broadcast block must feature newly synthesized content from fresh signals, managed via a rolling 2-session lookahead queue.  
*   
* **Legal & Copyright-Safe (Transformative Fair Use):** Ingest only unauthenticated public feeds (RSS, JSON APIs, WebSockets). Never read third-party articles verbatim; synthesize multi-source facts into original editorial commentary.  
*   
* **Full Broadcast Auditability:** Every aired script, source URL, and model execution must be permanently logged in PostgreSQL before going live.  
* 

## **2\. Programming Schedule & Signal Sources**

The station cycles through four distinct 30-minute topical shows (48 unique sessions/day), hosted by a single consistent AI DJ persona:

| Show Block (30 Mins) | Show Title | Approved Clean Signal Sources | Editorial Focus |
| :---- | :---- | :---- | :---- |
| **:00 – :30** | **Open Source Pulse** | • GitHub Trending RSS feeds |  |

• Hacker News API (/v0/topstories.json)

• Reddit r/opensource & r/selfhosted .json | New repositories, developer tools, license changes, and architectural debates. |  
| **:30 – :60** | **AI & Startup Capital** | • TechCrunch & Crunchbase News RSS

• Y Combinator Launch RSS

• Bluesky Public Firehose (app.bsky.feed.searchPosts) | Seed/Series funding rounds, valuation trends, problem statements, and market shifts. |  
| **:00 – :30** | **ArXiv & Lab Notes** | • ArXiv Daily RSS (cs.AI, cs.LG, cs.CL)

• Hugging Face Daily Papers JSON API | Plain-English breakdowns of new research papers, benchmarks, and practical applications. |  
| **:30 – :60** | **Big Ideas & Tech Culture** | • TED Talks Daily RSS

• Reddit r/technology .json & Lobste.rs RSS | Deep-dive synthesis connecting engineering culture, tech ethics, and macro ideas. |

## **3\. System Architecture & Rolling 2-Session Pipeline**

\[Layer 1: Collector & 2-Stage Deduplicator (Runs every 10 mins)\]  
Public RSS / JSON / Bluesky ──► URL & Title Hash Check ──► TF-IDF Similarity Cluster ──► Supabase (unbroadcasted)  
                                                                                                  │  
\[Layer 2: Rolling 2-Session Producer (Triggered when Queue Depth \< 2)\]                            ▼  
Pulls newest unbroadcasted clusters for next show ──► Multi-LLM Rewriter ──► TTS \+ Audio Mix ──► \[Local & HF Queue (Max 2)\]  
                                                                                                  │  
\[Layer 3: Zero-Transcode Broadcast Streamer (24/7 Continuous)\]                                    ▼  
FFmpeg (-c:v copy \-c:a copy) \+ Pre-rendered Visual Loop ──► RTMPS (Port 443\) ──► YouTube Live

### **Layer 1: Signal Collection & Two-Stage Deduplication**

1. **Stage 1 (Hard Dedup):** Normalize canonical URLs and strip titles to generate a SHA-256 hash. Reject any item already present in [Supabase](https://supabase.com/?utm_source=gemini).  
2.   
3. **Stage 2 (Semantic Story Clustering):** Run lightweight scikit-learn TF-IDF cosine similarity (threshold \>= 0.65) against active stories from the past 48 hours. Group multiple articles covering the same event into a single story\_cluster so the DJ synthesizes them once rather than repeating the same news from different outlets.  
4. 

### **Layer 2: The Rolling 2-Session Lookahead Producer**

* **Strict Queue Depth of 2:** The system never generates a full day of content in advance, nor does it generate audio live on-air. It maintains **1 currently playing session \+ 2 pre-rendered upcoming sessions** (a 60-minute safety buffer).  
*   
* **Trigger Mechanism:** The moment Session N finishes airing and Session N+1 begins streaming, the queue depth drops to 1 (Session N+2). This immediately triggers the producer worker to pull the latest unbroadcasted clusters from [Supabase](https://supabase.com/?utm_source=gemini) and build Session N+3.  
*   
* **6-Segment Script Generation (\~4,000 Words / 30 Mins):** To prevent LLM output truncation, each 30-minute show is generated across **6 sequential 5-minute blocks** (\~650 words per prompt) while passing a rolling summary of previous blocks for smooth transitions:  
* 

  1. 00–05m: Cold Open Hook \+ Lead Breaking Story Deep Dive.  
  2.   
  3. 05–10m: Secondary Stories \+ Engineering/Market Impact.  
  4.   
  5. 10–15m: Community Pulse (Synthesizing Hacker News/Reddit/Bluesky reactions).  
  6.   
  7. 15–20m: Under-the-Radar Spotlight (Niche repo, paper, or early startup).  
  8.   
  9. 20–25m: The Contrarian Take (Critical analysis & devil's advocate perspective).  
  10.   
  11. 25–30m: Rapid-Fire Recap \+ Teaser for the next 30-minute show in the queue.  
  12. 

### **Layer 3: Zero-Transcode Broadcast Streamer**

* **Pre-Rendered Visual Asset:** A single 10-second looping .mp4 animation (1280x720, 30fps, H.264, keyframe interval \-g 60) is generated once and stored permanently.  
*   
* **Audio Standardization:** All synthesized speech and background music ducking are exported as .aac (128 kbps, 44.1 kHz, stereo) to match YouTube's ingest spec.  
*   
* **Stream-Copy Muxing (**\<1% CPU**):** FFmpeg runs with \-c:v copy \-c:a copy, avoiding real-time video encoding on the cloud CPU.  
*   
* **Firewall-Safe Egress:** Streams over encrypted **RTMPS (**TCP Port 443**)** (rtmps://a.rtmps.youtube.com/live2/\$YOUTUBE\_STREAM\_KEY) to bypass container restrictions on standard port 1935.  
* 

## **4\. Multi-Provider LLM & Unlimited TTS Stack**

### **Multi-Provider LLM Router (Token-Bucket \+ Automatic Failover)**

All LLM calls route through a unified Python wrapper that inspects HTTP 429 status codes and x-ratelimit-remaining-\* headers, rotating across providers and organization keys:

| Priority | Provider | Account Pool | Target Models | Assigned Pipeline Role |
| :---- | :---- | :---- | :---- | :---- |
| **1 (Primary Writer)** | **Cerebras** | 1 Free Account (1M TPD) | llama-3.3-70b / qwen-3-32b | Writing the 6x650-word engaging radio scripts every 30 minutes. |
| **2 (Filter & Backup)** | **Groq** | 2 Separate Org Keys | llama-3.1-8b-instant (500K TPD/org) |  |

llama-3.3-70b-versatile (100K TPD/org) | Scoring clusters, extracting key facts, and primary failover for script writing. |  
| **3 (Long Context)** | **Google Gemini API** | 1 Free Project | gemini-2.5-flash / gemini-2.5-flash-lite | Digesting dense ArXiv research abstracts and long TED descriptions. |  
| **4 (Emergency)** | **OpenRouter** | 1 Free Account | \*:free model routes | Last-resort fallback if all primary quotas experience simultaneous rate limits. |

### **Unlimited TTS Voice Router (Decoupled from Groq)**

1. **Primary TTS (**edge-tts**):** Uses Microsoft Edge's keyless neural TTS library (en-US-AndrewMultilingualNeural or en-US-BrianMultilingualNeural). Zero cost, no character caps, and \<20 MB RAM overhead.  
2.   
3. **Offline Fallback (**Kokoro-82M **ONNX):** Packaged inside the container (327 MB model weights running on CPU via onnxruntime). If edge-tts experiences network throttling, Kokoro-82M synthesizes speech locally on the CPU with zero external rate limits.  
4. 

## **5\. Cloud Infrastructure & Storage Spec (Zero-Card Setup)**

### **Compute Host: [Hugging Face Spaces](https://huggingface.co/spaces?utm_source=gemini) (Docker SDK)**

* **Hardware Tier:** cpu-basic (**2 vCPUs, 16 GB RAM, 50 GB ephemeral disk** — 100% free, no credit card).  
*   
* **Container Environment Rules:**  
* 

  * As noted in the [NextWork RAG System Guide](https://nextwork.ai/projects/bc0e6d27-0232-4961-8c8d-1330d7f9233b?utm_source=gemini), Hugging Face Spaces requires Docker containers to run as **non-root user ID** 1000 and expose **Port** 7860.  
  *   
  * All runtime audio rendering, FFmpeg playlists, and model caches must write to /tmp (or /home/user/app/tmp owned by UID 1000).  
  *   
* **Anti-Sleep Keep-Alive:** A lightweight FastAPI server runs on port 7860 exposing GET /health (returning current on-air show, queue status, and uptime). An external free cron service ([Cron-job.org](https://cron-job.org/?utm_source=gemini) or [UptimeRobot](https://uptimerobot.com/?utm_source=gemini)) pings /health every 10 minutes to prevent the Space from entering sleep mode.  
* 

### **Database & Safety Audit Log: [Supabase](https://supabase.com/?utm_source=gemini) (PostgreSQL)**

Uses the 500 MB free tier to store deduplication state and permanent compliance records (\~36 MB/month growth rate):

* raw\_signals **Table:**  
* 

  * id (UUID, Primary Key)  
  *   
  * url\_hash (TEXT, UNIQUE, Indexed)  
  *   
  * source\_url (TEXT)  
  *   
  * title (TEXT)  
  *   
  * summary\_text (TEXT)  
  *   
  * show\_category (ENUM: open\_source, ai\_funding, research, tech\_culture)  
  *   
  * cluster\_id (UUID, Foreign Key)  
  *   
  * ingested\_at (TIMESTAMPTZ)  
  *   
* story\_clusters **Table:**  
* 

  * cluster\_id (UUID, Primary Key)  
  *   
  * canonical\_headline (TEXT)  
  *   
  * show\_category (TEXT)  
  *   
  * source\_count (INT)  
  *   
  * is\_broadcasted (BOOLEAN, Default FALSE, Indexed)  
  *   
  * created\_at (TIMESTAMPTZ)  
  *   
* broadcast\_audit\_log **Table (Safety & Compliance Record):**  
* 

  * session\_id (UUID, Primary Key)  
  *   
  * show\_category (TEXT)  
  *   
  * scheduled\_start\_at (TIMESTAMPTZ)  
  *   
  * actual\_aired\_at (TIMESTAMPTZ)  
  *   
  * full\_script\_transcript (TEXT — exact verbatim words synthesized)  
  *   
  * cited\_source\_urls (JSONB — array of all source URLs used in the show)  
  *   
  * llm\_provider\_model (TEXT)  
  *   
  * tts\_engine\_used (TEXT)  
  *   
  * hf\_audio\_backup\_path (TEXT)  
  * 

### **Media & Asset Vault: Private Hugging Face Dataset**

* A separate **Private Hugging Face Dataset** repo acts as free cloud object storage accessed via huggingface\_hub (HF\_TOKEN).  
*   
* Stores the master radio\_visual\_loop.mp4, station transition jingles, and a rolling 7-day backup of rendered .aac session files.  
* 

## **6\. Crash Recovery & Cold-Start Protocol**

Because container local disks reset on redeployment or host migration, the startup entrypoint script executes a stateless recovery sequence before launching the stream:

1. **Fetch Static Assets:** Download radio\_visual\_loop.mp4 and station jingles from the Private HF Dataset into /tmp/assets.  
2.   
3. **Check Queue State:** Query [Supabase](https://supabase.com/?utm_source=gemini) broadcast\_audit\_log for any pre-rendered session stored in the Private HF Dataset that has actual\_aired\_at \= NULL.  
4.   
5. **Emergency Bootstrap (If Queue \= 0):** Immediately synthesize a rapid 5-minute "Station Reboot & Breaking Headlines" intro block (\~90 seconds to render via edge-tts) so the FFmpeg stream goes live on YouTube immediately while the background producer builds the first full 30-minute session.  
6. 

Would you like to review or adjust any part of this specs.md, or should we move straight to setting up the **Supabase SQL schema and project directory structure**?

\=============================
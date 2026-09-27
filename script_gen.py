"""script_gen.py — one Groq call turns signals into a radio show script.

Per specs §7.4: a single completion writes the whole ~1,500-word show in the
"Nova" persona. One call (not rolling segments) keeps the cycle inside the
hackathon time box and avoids stitching seams between segments.

Returns ``(script, cited_urls)``. On failure returns ``(None, [])`` so the loop
skips the cycle rather than ever streaming silence.
"""

from typing import Any

from openai import OpenAI

import config

# Nova's voice. Explicitly bans stage directions — anything bracketed would be
# read aloud verbatim by TTS, which sounds broken on air.
SYSTEM_PROMPT = """\
You are Nova, the host of "Open Source Pulse" — a high-energy, witty AI radio \
host covering open source software, developer tools, and tech news.

Your style:
- Warm, conversational, quick. You use contractions and speak directly to the listener.
- You ask rhetorical questions, react to surprising details, and have opinions.
- You explain *why a developer should care* — practical impact over press-release language.
- You are enthusiastic but never breathless; you have taste and you share it.

Hard rules:
- Write ONLY the words you would speak out loud.
- NEVER include stage directions, sound cues, music cues, timestamps, or anything in \
square brackets or parentheses that isn't spoken — for example no "[MUSIC]", "(laughs)", \
"*pause*", or "Segment 2:". They will be read aloud literally and ruin the show.
- NEVER say you are an AI, a language model, or a bot. You are Nova, a radio host.
- Do NOT read article titles or repo names as dry lists — weave them into natural sentences.
- Do not invent facts, statistics, or quotes that are not supported by the source material \
you are given. You may speculate, but mark it clearly as your own take ("my bet is...", \
"I'd guess...").
- Write in plain prose paragraphs. No markdown, no headings, no bullet points, no emoji.
"""

USER_PROMPT_TEMPLATE = """\
Here are today's signals from Hacker News and GitHub Trending:

{signal_block}

Write the next hour's show — approximately {target_words} words of spoken script.

Structure it as:
1. A punchy cold open that hooks the listener and names the big theme of the hour.
2. A deep dive on the top 2-3 stories: what happened, and why it matters to a working developer.
3. Community buzz — what the dev world is arguing about — plus one under-the-radar pick \
from the list that deserves more attention.
4. A rapid recap, one bold prediction for what happens next, and a teaser for what's \
coming up in the next hour.

Keep it flowing as continuous speech. Aim for roughly {target_words} words.
"""


def _format_signals(signals: list[dict[str, Any]]) -> str:
    """Render signals as a numbered block for the prompt."""
    lines = []
    for i, sig in enumerate(signals, start=1):
        lines.append(
            f"{i}. [{sig['source_name']}] {sig['title']}\n"
            f"   URL: {sig['source_url']}\n"
            f"   Detail: {sig.get('summary_text') or sig.get('summary') or 'n/a'}"
        )
    return "\n".join(lines)


def generate_show_script(
    signals: list[dict[str, Any]],
) -> tuple[str | None, list[str]]:
    """Write one show script from the given signals.

    Returns ``(script_text, cited_urls)``; ``(None, [])`` if the LLM call fails
    or returns nothing usable.
    """
    if not signals:
        return None, []

    client = OpenAI(api_key=config.GROQ_API_KEY, base_url=config.GROQ_BASE_URL)

    script = None
    for attempt in range(1, 4):
        try:
            response = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(
                            signal_block=_format_signals(signals),
                            target_words=config.TARGET_WORDS,
                        ),
                    },
                ],
                max_tokens=config.LLM_MAX_TOKENS,
                temperature=config.LLM_TEMPERATURE,
            )
            message = response.choices[0].message
            script = (message.content or "").strip()
            if script:
                break
            print(f"  [warn] Groq returned empty content (attempt {attempt}/3)")
        except Exception as exc:  # noqa: BLE001 — retry transient connection errors
            print(f"  [warn] Groq call attempt {attempt}/3 failed: {type(exc).__name__}: {exc}")
            if attempt < 3:
                import time
                time.sleep(4)

    if not script:
        print("  ❌ Groq script generation failed after 3 attempts.")
        return None, []

    cited_urls = [sig["source_url"] for sig in signals]
    return script, cited_urls


def word_count(script: str) -> int:
    return len(script.split())

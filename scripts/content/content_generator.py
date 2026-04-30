"""Generates deep content ideas and full content packs (Form 1 — daily)."""

import os
import json
from anthropic import Anthropic
from prompts.voice_context import VOICE_SYSTEM_PROMPT

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def generate_ideas(articles: list[dict]) -> list[dict]:
    """Given articles, return 3-5 strong content opportunities with angles."""
    articles_text = "\n".join(
        f"- {a['title']} ({a['source']}): {a['summary'][:200]}"
        for a in articles[:35]
    )

    resp = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=[{"type": "text", "text": VOICE_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"""Here are today's news articles. Identify the 3-5 best content opportunities for Muneeb's social media.

Articles:
{articles_text}

For each opportunity return a JSON object with:
- title: punchy title for the idea
- trend: what is happening (1 sentence, specific)
- consensus: what most people are saying or thinking
- angle: Muneeb's contrarian or deeper angle (specific, data-driven, not vague)
- urgency: "breaking" | "timely" | "evergreen"
- pillar: which content pillar (fintech/mena/saas-ai/private-markets/pakistan)

Return a JSON array. Only include ideas with enough public data for an Akash-style analytical post (3+ verifiable stats). Skip soft news, opinion pieces without data, and topics outside the 5 pillars.""",
        }],
    )

    try:
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"Ideas parse error: {e}\nRaw: {resp.content[0].text[:300]}")
        return []


def generate_full_pack(idea: dict) -> dict:
    """Generate X post, thread, LinkedIn, and Substack draft for one idea."""
    resp = _get_client().messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=[{"type": "text", "text": VOICE_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"""Generate a complete content pack for this idea.

Topic: {idea.get('title')}
Trend: {idea.get('trend')}
Consensus view: {idea.get('consensus')}
Our angle: {idea.get('angle')}

Return a JSON object with exactly these 4 keys:

"x_longform": A 250-310 word analytical post. Akash style strictly. Thesis in sentence 1. 5+ specific numbers. Zero em dashes. Zero first-person. Closes with one reframing sentence.

"x_thread": Array of 6-8 tweet strings. Tweet 1 is standalone hook. Each tweet advances the argument. Final tweet: sharpest insight + soft CTA (no hard sell, no link in tweet body).

"linkedin": 200-260 word post. Opens with paradox. "My hypothesis:" mid-post. Evidence block with numbers. Closes with open question. First-person and em dashes allowed.

"substack_draft": Structured outline: headline, subheadline, 5-6 section headers each with 2-sentence description of what that section covers. Ends with closing thesis sentence.

Return only valid JSON. No markdown wrapping.""",
        }],
    )

    try:
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception as e:
        print(f"Pack parse error: {e}")
        return {"raw": resp.content[0].text}

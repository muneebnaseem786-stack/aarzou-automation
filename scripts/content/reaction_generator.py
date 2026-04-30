"""Generates quick reaction posts from breaking news (Form 2 — every 2 hours)."""

import os
import json
from datetime import datetime, timezone
from anthropic import Anthropic
from prompts.voice_context import VOICE_SYSTEM_PROMPT

_client = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def generate_reaction_posts(articles: list[dict]) -> list[dict]:
    """Generate 2-3 quick reaction posts from recent articles."""
    if not articles:
        print("No articles to react to")
        return []

    articles_text = "\n".join(
        f"- {a['title']} ({a['source']}): {a['summary'][:250]}"
        for a in articles[:20]
    )

    resp = _get_client().messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2500,
        system=[{"type": "text", "text": VOICE_SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{
            "role": "user",
            "content": f"""Recent news (last few hours):
{articles_text}

Generate 2-3 quick reaction posts for Muneeb's social media. Only react to genuinely interesting developments in his content pillars. Skip routine/boring updates. Quality over quantity.

For each post return a JSON object with:
- platform: "X" or "substack_note"
- topic: the story being reacted to (10 words max)
- source_headline: exact headline that triggered this
- content: the post text
  X post: 1-4 sentences. Opens with thesis or striking fact. Uses "My read:" construction. No hashtags. No emojis.
  Substack Note: 100-150 words. Sharp observation with one specific number. "My read:" or "My take:". Ends with open question.

Return a JSON array. If nothing is genuinely interesting, return an empty array rather than forcing mediocre content.""",
        }],
    )

    try:
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        posts = json.loads(text)
        now = datetime.now(timezone.utc).isoformat()
        for post in posts:
            post["generated_at"] = now
            post["status"] = "pending"
        return posts
    except Exception as e:
        print(f"Reaction parse error: {e}\nRaw: {resp.content[0].text[:300]}")
        return []

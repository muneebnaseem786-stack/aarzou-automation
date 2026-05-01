"""
Generates daily reply suggestions for @FortuneAndRuin.

Scans Reddit for trending finance/economics topics, then generates
3 reply options per topic — short punchy historical parallels that
add value to posts from established accounts.

Sends each suggestion to Telegram as a plain message ready to copy.

Usage:
    python fortune_ruin/scripts/generate_reply_suggestions.py
"""

import sys
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)

TARGET_ACCOUNTS = [
    "@morganhousel",
    "@kylascanlon",
    "@scottgalloway",
    "@LynAldenContact",
    "@EconomicsPics",
    "@RaoulGMI",
    "@bespokeinvest",
    "@NickTimiraos",      # WSJ Fed reporter
    "@conorsen",          # macro
]

SUBREDDITS = ["economics", "finance", "MacroEconomics", "geopolitics", "collapse"]


# ── Reddit signal fetcher ─────────────────────────────────────────────────────

def fetch_reddit_trends(max_topics: int = 5) -> list[dict]:
    """Fetch top trending posts from finance subreddits. Returns list of {topic, context}."""
    trends = []
    headers = {"User-Agent": "FortuneAndRuin-bot/1.0"}

    for sub in SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=day&limit=5"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                d = post.get("data", {})
                if d.get("score", 0) < 50:
                    continue
                trends.append({
                    "topic": d.get("title", "")[:120],
                    "context": f"r/{sub} — {d.get('score', 0)} upvotes",
                    "subreddit": sub,
                })
        except Exception:
            continue

    # Deduplicate similar topics and cap
    seen = set()
    unique = []
    for t in trends:
        key = t["topic"][:40].lower()
        if key not in seen:
            seen.add(key)
            unique.append(t)
        if len(unique) >= max_topics:
            break

    return unique


# ── Reply generation ──────────────────────────────────────────────────────────

def generate_replies(topic: str, reddit_context: str) -> list[dict]:
    """Generate 3 reply suggestions for a trending topic."""
    from engine.claude_client import load_prompt, call_claude_json

    template = load_prompt("x_reply_prompt")
    prompt = template.format(topic=topic, reddit_context=reddit_context)
    result = call_claude_json(prompt, max_tokens=1000)
    return result.get("replies", [])


# ── Telegram sender ───────────────────────────────────────────────────────────

def _tg_token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]

def _tg_chat_id() -> str:
    return os.environ["YOUR_TELEGRAM_CHAT_ID"]

def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{_tg_token()}/sendMessage",
        json={"chat_id": _tg_chat_id(), "text": text},
        timeout=15,
    )


def format_suggestion(topic: str, reply: dict, index: int, total: int) -> str:
    accounts = " ".join(TARGET_ACCOUNTS[:4])
    lines = [
        f"💬 Reply Suggestion {index}/{total}",
        f"Topic: {topic}",
        "",
        reply["text"],
        "",
        f"Best on: {reply.get('best_on', 'posts about this topic')}",
        f"Try: {accounts}",
    ]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    uae = datetime.now(timezone.utc) + timedelta(hours=4)
    print(f"[replies] Generating reply suggestions — {uae.strftime('%d %b %H:%M UAE')}")

    print("[replies] Fetching Reddit trends...")
    trends = fetch_reddit_trends(max_topics=3)

    if not trends:
        send_telegram("💬 No strong Reddit trends today — skip reply suggestions.")
        print("[replies] No trends found.")
        return

    send_telegram(
        f"💬 Fortune & Ruin — Daily Reply Suggestions\n"
        f"{uae.strftime('%d %b')} · {len(trends)} topics · copy and reply on X"
    )

    total_sent = 0
    for trend in trends:
        topic = trend["topic"]
        context = trend["context"]
        print(f"[replies] Generating for: {topic[:60]}...")

        try:
            replies = generate_replies(topic, context)
        except Exception as e:
            print(f"[replies] Error generating for '{topic[:40]}': {e}")
            continue

        for i, reply in enumerate(replies[:3], 1):
            msg = format_suggestion(topic, reply, i, min(3, len(replies)))
            send_telegram(msg)
            total_sent += 1

    print(f"[replies] Done. Sent {total_sent} suggestions to Telegram.")


if __name__ == "__main__":
    main()

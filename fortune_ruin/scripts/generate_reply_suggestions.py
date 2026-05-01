"""
Generates daily reply suggestions for @FortuneAndRuin.

Fetches real recent posts from target finance accounts via Nitter RSS,
then generates one targeted reply per post using the F&R forensic angle.

Each Telegram message contains:
  - The original post text
  - A pre-written reply ready to copy
  - A direct link to reply at

Usage:
    python fortune_ruin/scripts/generate_reply_suggestions.py
"""

import sys
import os
import json
import re
import xml.etree.ElementTree as ET
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


# ── Config ────────────────────────────────────────────────────────────────────

TARGET_ACCOUNTS = [
    "morganhousel",
    "kylascanlon",
    "LynAldenContact",
    "EconomicsPics",
    "NickTimiraos",
    "bespokeinvest",
    "RaoulGMI",
    "saxena_puru",
    "Nouriel",
]

# Nitter instances as fallbacks (public, no auth)
NITTER_INSTANCES = [
    "nitter.poast.org",
    "nitter.privacydev.net",
    "nitter.net",
    "nitter.it",
]

MIN_POST_CHARS = 60   # skip very short posts
MAX_POSTS_PER_ACCOUNT = 3
MAX_SUGGESTIONS = 5   # total to send per day


# ── Nitter RSS fetcher ────────────────────────────────────────────────────────

def fetch_recent_posts(username: str) -> list[dict]:
    """Fetch recent posts from a target account via Nitter RSS. Returns list of {text, url, author}."""
    for instance in NITTER_INSTANCES:
        try:
            url = f"https://{instance}/{username}/rss"
            resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            channel = root.find("channel")
            if channel is None:
                continue

            posts = []
            for item in channel.findall("item")[:MAX_POSTS_PER_ACCOUNT]:
                title = item.findtext("title", "")
                link  = item.findtext("link", "")
                desc  = item.findtext("description", "")

                # Strip HTML tags from description
                text = re.sub(r"<[^>]+>", "", desc).strip()
                text = text or title

                # Convert nitter link to x.com link
                x_link = link.replace(f"https://{instance}/", "https://x.com/")

                if len(text) < MIN_POST_CHARS:
                    continue
                if "RT by" in title:  # skip retweets
                    continue

                posts.append({
                    "text": text[:300],
                    "url": x_link,
                    "author": username,
                })

            if posts:
                return posts

        except Exception:
            continue

    return []


# ── Reply generation ──────────────────────────────────────────────────────────

def generate_reply(original_post: str, author: str) -> str:
    """Generate one targeted reply to a specific post."""
    from engine.claude_client import call_claude

    prompt = f"""You write replies for @FortuneAndRuin — a forensic financial history account — to posts from finance influencers on X.

ORIGINAL POST by @{author}:
"{original_post}"

Write ONE reply that adds a specific historical fact or parallel that the original post doesn't mention. The reply must make @{author} want to like or respond to it.

RULES:
- Under 220 characters (leaves room to quote the original)
- Adds one specific date, name, or number not in the original post
- Present tense for historical events
- No em-dashes. No negative constructions. No hedging.
- Does not start with "I", "We", "Great point", or "Actually"
- Sounds like a knowledgeable person, not a brand account
- Ends with a flat statement or implicit question — never an explicit "what do you think?"

Return ONLY the reply text. No quotes, no preamble."""

    return call_claude(prompt, max_tokens=200).strip().strip('"')


# ── Telegram ──────────────────────────────────────────────────────────────────

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

def format_suggestion(post: dict, reply: str, index: int, total: int) -> str:
    return (
        f"💬 Reply {index}/{total} — @{post['author']}\n"
        f"─────────────────────────────\n"
        f"Their post:\n"
        f"\"{post['text'][:200]}\"\n"
        f"\n"
        f"Your reply (copy this):\n"
        f"{reply}\n"
        f"\n"
        f"Reply here: {post['url']}"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    uae = datetime.now(timezone.utc) + timedelta(hours=4)
    print(f"[replies] {uae.strftime('%d %b %H:%M UAE')}")

    # Collect posts from target accounts
    all_posts = []
    for username in TARGET_ACCOUNTS:
        print(f"[replies] Fetching @{username}...")
        posts = fetch_recent_posts(username)
        all_posts.extend(posts)
        if len(all_posts) >= MAX_SUGGESTIONS * 2:
            break

    if not all_posts:
        send_telegram("💬 Could not fetch posts from target accounts today. Try again later.")
        print("[replies] No posts fetched.")
        return

    # Pick the best posts (limit to MAX_SUGGESTIONS)
    selected = all_posts[:MAX_SUGGESTIONS]

    send_telegram(
        f"💬 Fortune & Ruin — Reply Suggestions\n"
        f"{uae.strftime('%d %b')} · {len(selected)} replies ready to copy and post"
    )

    for i, post in enumerate(selected, 1):
        print(f"[replies] Generating reply for @{post['author']} post...")
        try:
            reply = generate_reply(post["text"], post["author"])
            msg = format_suggestion(post, reply, i, len(selected))
            send_telegram(msg)
        except Exception as e:
            print(f"[replies] Error: {e}")
            continue

    print(f"[replies] Done. Sent {len(selected)} suggestions.")


if __name__ == "__main__":
    main()

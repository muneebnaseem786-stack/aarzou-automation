"""
Generates a daily X post for @FortuneAndRuin and sends it to Telegram for approval.

Runs via GitHub Actions at noon and 5pm UAE time.
User replies YES to post, NO to skip.

Usage:
    python fortune_ruin/scripts/generate_daily_post.py [post_type]
    post_type: financial_history_thread | hot_take | behind_the_scenes (default: auto)
"""

import sys
import os
import json
import re
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

# Allow imports from fortune_ruin/engine and fortune_ruin/db
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ── Telegram helpers ──────────────────────────────────────────────────────────

def _tg_token() -> str:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    return token


def _tg_chat_id() -> str:
    chat_id = os.environ.get("YOUR_TELEGRAM_CHAT_ID", "")
    if not chat_id:
        raise RuntimeError("YOUR_TELEGRAM_CHAT_ID not set")
    return chat_id


def send_telegram(text: str) -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{_tg_token()}/sendMessage",
        json={"chat_id": _tg_chat_id(), "text": text},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ── Post type selection ───────────────────────────────────────────────────────

POST_TYPE_LABELS = {
    "financial_history_thread": "Financial History Thread",
    "hot_take":                 "Hot Take",
    "behind_the_scenes":        "Behind the Scenes",
    "video_promotion":          "Video Promotion",
}

def pick_post_type() -> str:
    """
    noon slot (8am UTC): always financial_history_thread
    5pm slot (1pm UTC): hot_take Mon/Wed/Fri, behind_the_scenes Tue/Thu/Sat/Sun
    """
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    weekday = now_utc.weekday()  # 0=Mon, 6=Sun

    if hour < 11:   # morning slot (8am UTC = noon UAE)
        return "financial_history_thread"
    else:           # afternoon slot (1pm UTC = 5pm UAE)
        return "hot_take" if weekday in (0, 2, 4) else "behind_the_scenes"


def build_context(post_type: str) -> str:
    now_utc = datetime.now(timezone.utc)
    if post_type == "financial_history_thread":
        return (
            "Pick a compelling financial history event or figure that illustrates the "
            "'beneficiary framing' — who profited from a system that harmed others. "
            "Must work as a standalone viral thread with no video context. "
            f"Today is {now_utc.strftime('%B %Y')}."
        )
    elif post_type == "hot_take":
        return (
            "Connect a current financial or macroeconomic phenomenon (tariffs, central bank policy, "
            "inflation, debt ceilings, tech valuations) to a precise historical parallel using the "
            "Fortune & Ruin forensic lens. Name the mechanism, name the historical actor, name the outcome."
        )
    elif post_type == "behind_the_scenes":
        return (
            "We are actively researching our next Fortune & Ruin episode on financial history. "
            "Share a striking single fact or quote from financial history research — "
            "something that would make a reader stop and say 'I had no idea'. "
            "Keep it under 2 tweets."
        )
    return "Generate a compelling X post for the Fortune & Ruin financial history channel."


# ── Post generation ───────────────────────────────────────────────────────────

def generate_post(post_type: str, context: str) -> list[str]:
    """Generate tweet content via Claude. Returns list of tweet strings."""
    from engine.x_content_generator import generate_x_post
    result = generate_x_post(post_type, context)
    tweets = result.get("tweets", [])
    return [tw["content"] for tw in tweets]


# ── Format Telegram message ───────────────────────────────────────────────────

def format_message(post_type: str, tweets: list[str], slot_label: str) -> str:
    label = POST_TYPE_LABELS.get(post_type, post_type)

    lines = [
        f"🐦 Fortune & Ruin — Daily X Post",
        f"Type: {label} | {slot_label}",
        "",
        "─────────────────────────────",
    ]

    for i, tweet in enumerate(tweets, 1):
        lines.append(f"Tweet {i}/{len(tweets)}:")
        lines.append(tweet)
        lines.append("")

    lines += [
        "─────────────────────────────",
        "Reply YES to post to @FortuneAndRuin",
        "Reply NO to skip",
        "",
        # Machine-readable block parsed by process_telegram_approvals.py
        f"TWEETS_JSON:{json.dumps(tweets)}",
    ]

    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # Allow manual override: python generate_daily_post.py hot_take
    if len(sys.argv) > 1 and sys.argv[1] in POST_TYPE_LABELS:
        post_type = sys.argv[1]
    else:
        post_type = pick_post_type()

    now_utc = datetime.now(timezone.utc)
    uae = now_utc + timedelta(hours=4)
    slot_label = uae.strftime("%d %b, %I:%M %p UAE")

    print(f"[generate] Post type: {post_type}")
    print(f"[generate] Slot: {slot_label}")

    context = build_context(post_type)
    print("[generate] Calling Claude...")
    tweets = generate_post(post_type, context)
    print(f"[generate] Got {len(tweets)} tweets")

    message = format_message(post_type, tweets, slot_label)
    result = send_telegram(message)

    if result.get("ok"):
        msg_id = result["result"]["message_id"]
        print(f"[generate] Sent to Telegram (message_id={msg_id})")
        print("[generate] Done. Reply YES or NO in Telegram.")
    else:
        print(f"[generate] Telegram error: {result}")
        sys.exit(1)


if __name__ == "__main__":
    main()

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
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


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

def send_thread_as_messages(tweets: list[str], post_type: str) -> bool:
    """Send each tweet as its own Telegram message, then a final prompt."""
    for i, tweet in enumerate(tweets):
        # Add thread indicator to first tweet of multi-tweet posts
        text = tweet
        if i == 0 and len(tweets) > 1:
            text = tweet + " 🧵"
        result = send_telegram(text)
        if not result.get("ok"):
            return False

    label = "tweet" if len(tweets) == 1 else "tweets above"
    send_telegram(f"({len(tweets)} {label}) — Reply YES when posted on X, NO to skip.")
    return True


# ── Typefully integration ─────────────────────────────────────────────────────

def create_typefully_draft(tweets: list[str]) -> str:
    """
    Creates a thread draft in Typefully. Returns the draft URL, or empty string on failure.
    Requires TYPEFULLY_API_KEY in env.
    Thread format: tweets joined by double-newline + --- separator.
    """
    api_key = os.environ.get("TYPEFULLY_API_KEY", "")
    if not api_key:
        return ""

    content = "\n\n---\n\n".join(tweets)
    try:
        resp = requests.post(
            "https://api.typefully.com/v1/drafts/",
            headers={"X-API-KEY": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"content": content, "threadify": False},
            timeout=15,
        )
        if resp.status_code in (200, 201):
            data = resp.json()
            # Typefully returns share_url or we build it from the id
            return data.get("share_url") or data.get("url") or ""
    except Exception as e:
        print(f"[generate] Typefully error (non-fatal): {e}")
    return ""


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

    # Save for logging when user confirms YES
    _save_last_post(tweets, post_type)

    ok = send_thread_as_messages(tweets, post_type)
    if ok:
        print(f"[generate] Sent {len(tweets)} messages to Telegram.")
    else:
        print("[generate] Telegram send failed.")
        sys.exit(1)


def _save_last_post(tweets: list[str], post_type: str):
    """Persist last generated post so approval script can log it on YES."""
    topic = tweets[0][:80] if tweets else "unknown"
    data = json.dumps({"tweets": tweets, "post_type": post_type, "topic": topic})

    # Local file (works when running from the laptop)
    last_post_file = Path(__file__).parent.parent / ".last_post.json"
    last_post_file.write_text(data, encoding="utf-8")

    # GitHub repo variable (works in GitHub Actions)
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if repo and token:
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        payload = {"name": "FR_LAST_POST_JSON", "value": data}
        url = f"https://api.github.com/repos/{repo}/actions/variables/FR_LAST_POST_JSON"
        resp = requests.patch(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 404:
            requests.post(
                f"https://api.github.com/repos/{repo}/actions/variables",
                json=payload, headers=headers, timeout=10,
            )


if __name__ == "__main__":
    main()

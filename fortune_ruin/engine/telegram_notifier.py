"""
Telegram notifier — sends X post drafts to Telegram for approval.
"""

import os
import json
import requests
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")

POST_TYPE_LABELS = {
    "financial_history_thread": "📜 Financial History Thread",
    "hot_take":                 "⚡ Hot Take",
    "behind_the_scenes":        "🔬 Behind the Scenes",
    "video_promotion":          "🎬 Video Promotion",
}


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id() -> str:
    return os.environ["YOUR_TELEGRAM_CHAT_ID"]


def send_message(text: str, parse_mode: str = "Markdown") -> dict:
    resp = requests.post(
        f"https://api.telegram.org/bot{_token()}/sendMessage",
        json={"chat_id": _chat_id(), "text": text, "parse_mode": parse_mode},
        timeout=10,
    )
    return resp.json()


def send_post_for_approval(db_post_id: int, post_type: str, tweets: list[dict]) -> bool:
    """
    Send a queued X post to Telegram for approval.
    Returns True if message was sent successfully.
    """
    label = POST_TYPE_LABELS.get(post_type, post_type)
    lines = [f"*{label}* — Post #{db_post_id}"]
    lines.append("─────────────────")

    for tw in tweets:
        lines.append(f"*{tw['tweet_number']}.* {tw['content']}")
        lines.append("")

    lines.append("─────────────────")
    lines.append(f"Reply *{db_post_id} yes* to post to X")
    lines.append(f"Reply *{db_post_id} no* to reject")

    result = send_message("\n".join(lines))
    return result.get("ok", False)


def send_batch_for_approval(posts: list[dict]) -> int:
    """
    Send multiple queued posts to Telegram.
    Returns number successfully sent.
    """
    sent = 0
    for post in posts:
        try:
            content = json.loads(post["content"])
            tweets = content.get("tweets", [])
            ok = send_post_for_approval(
                db_post_id=post["id"],
                post_type=post["post_type"],
                tweets=tweets,
            )
            if ok:
                sent += 1
        except Exception:
            continue
    return sent


def notify_posted(post_id: int, tweet_url: str):
    send_message(f"✅ Post #{post_id} posted to X\n{tweet_url}")


def notify_rejected(post_id: int):
    send_message(f"🗑️ Post #{post_id} rejected.")

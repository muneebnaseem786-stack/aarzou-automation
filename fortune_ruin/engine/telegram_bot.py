"""
Telegram approval bot — polls for replies and posts approved content to X.

Run this alongside the dashboard:
    python -m engine.telegram_bot

Commands accepted (in Telegram):
    "<post_id> yes"  — approve and post to X
    "<post_id> no"   — reject the post
    "list"           — show all pending posts
    "help"           — show commands
"""

import os
import sys
import json
import time
import requests
from pathlib import Path

# Make parent importable when run as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from db.database import get_x_posts, update_x_post_status, init_db
from engine.x_poster import post_thread, post_single
from engine.telegram_notifier import send_message, notify_posted, notify_rejected

POLL_INTERVAL = 3   # seconds between Telegram polls
_last_update_id = 0


def _token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]


def _chat_id() -> str:
    return os.environ["YOUR_TELEGRAM_CHAT_ID"]


def _get_updates() -> list[dict]:
    global _last_update_id
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{_token()}/getUpdates",
            params={"offset": _last_update_id + 1, "timeout": 2},
            timeout=10,
        )
        data = resp.json()
        if not data.get("ok"):
            return []
        updates = data.get("result", [])
        if updates:
            _last_update_id = updates[-1]["update_id"]
        return updates
    except Exception:
        return []


def _extract_text(update: dict) -> tuple[str, str] | None:
    """Returns (chat_id, text) or None if not a text message."""
    msg = update.get("message")
    if not msg:
        return None
    chat_id = str(msg.get("chat", {}).get("id", ""))
    text = msg.get("text", "").strip()
    if not text or chat_id != _chat_id():
        return None
    return chat_id, text


def _handle_approve(post_id: int):
    posts = get_x_posts("approved") + get_x_posts("draft") + get_x_posts("scheduled")
    post = next((p for p in posts if p["id"] == post_id), None)

    if not post:
        send_message(f"⚠️ Post #{post_id} not found or already handled.")
        return

    try:
        content = json.loads(post["content"])
        tweets = [tw["content"] for tw in content.get("tweets", [])]

        if len(tweets) == 1:
            tweet_id = post_single(tweets[0])
            tweet_ids = [tweet_id]
        else:
            tweet_ids = post_thread(tweets)

        update_x_post_status(post_id, "posted", tweet_ids[0])
        url = f"https://x.com/FortuneAndRuin/status/{tweet_ids[0]}"
        notify_posted(post_id, url)

    except Exception as e:
        send_message(f"❌ Failed to post #{post_id}: {e}")


def _handle_reject(post_id: int):
    update_x_post_status(post_id, "rejected")
    notify_rejected(post_id)


def _handle_list():
    posts = get_x_posts("draft") + get_x_posts("approved")
    if not posts:
        send_message("No pending posts in queue.")
        return
    lines = ["*Pending posts:*"]
    for p in posts[:10]:
        try:
            content = json.loads(p["content"])
            first_tweet = content["tweets"][0]["content"][:80]
        except Exception:
            first_tweet = str(p["content"])[:80]
        lines.append(f"*#{p['id']}* [{p['post_type']}] {first_tweet}…")
        lines.append(f"  → Reply `{p['id']} yes` to post or `{p['id']} no` to reject")
    send_message("\n".join(lines))


def _handle_help():
    send_message(
        "*Fortune & Ruin — X Approval Bot*\n\n"
        "`<id> yes` — post to X\n"
        "`<id> no` — reject\n"
        "`list` — show pending posts\n"
        "`help` — show this message"
    )


def process_update(text: str):
    text_lower = text.lower().strip()

    if text_lower == "help":
        _handle_help()
        return

    if text_lower == "list":
        _handle_list()
        return

    # Parse "<id> yes" or "<id> no"
    parts = text_lower.split()
    if len(parts) == 2 and parts[0].isdigit():
        post_id = int(parts[0])
        action = parts[1]
        if action in ("yes", "y", "approve", "post"):
            _handle_approve(post_id)
        elif action in ("no", "n", "reject", "skip"):
            _handle_reject(post_id)
        else:
            send_message(f"Unknown action '{action}'. Use `{post_id} yes` or `{post_id} no`.")
    else:
        send_message("Not sure what you mean. Send `help` to see commands.")


def run():
    init_db()
    send_message(
        "🤖 *Fortune & Ruin bot is online.*\n"
        "Send `help` to see commands or `list` to see pending posts."
    )
    print("Telegram bot running — waiting for messages...")

    while True:
        updates = _get_updates()
        for update in updates:
            result = _extract_text(update)
            if result:
                _, text = result
                try:
                    process_update(text)
                except Exception as e:
                    send_message(f"⚠️ Error: {e}")
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    run()

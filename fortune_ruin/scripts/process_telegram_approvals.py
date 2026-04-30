"""
Polls Telegram for YES/NO replies and posts approved X content automatically.

Runs every 15 minutes via GitHub Actions.
Tracks the last processed Telegram update_id in a GitHub repo variable
(FR_LAST_UPDATE_ID) so we never double-process.

Expected Telegram reply format:
    User replies to the bot's message with: YES  (or yes / y)
    Or: NO  (or no / n)

The bot message must contain a TWEETS_JSON: line (written by generate_daily_post.py).

Usage:
    python fortune_ruin/scripts/process_telegram_approvals.py
"""

import sys
import os
import json
import re
import requests
from pathlib import Path

# Allow imports from fortune_ruin/engine
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")


# ── Config ────────────────────────────────────────────────────────────────────

VARIABLE_NAME = "FR_LAST_UPDATE_ID"
YES_WORDS = {"yes", "y", "approve", "post", "👍"}
NO_WORDS  = {"no",  "n", "reject",  "skip", "👎"}


# ── Telegram helpers ──────────────────────────────────────────────────────────

def _tg_token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"]

def _tg_chat_id() -> str:
    return os.environ["YOUR_TELEGRAM_CHAT_ID"]


def get_updates(offset: int) -> list[dict]:
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{_tg_token()}/getUpdates",
            params={"offset": offset, "timeout": 5, "limit": 100},
            timeout=15,
        )
        data = resp.json()
        return data.get("result", []) if data.get("ok") else []
    except Exception as e:
        print(f"[approvals] getUpdates error: {e}")
        return []


def send_telegram(text: str):
    requests.post(
        f"https://api.telegram.org/bot{_tg_token()}/sendMessage",
        json={"chat_id": _tg_chat_id(), "text": text},
        timeout=10,
    )


# ── GitHub variable helpers (tracks last processed update_id) ─────────────────

def _gh_headers() -> dict:
    token = os.environ.get("GITHUB_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def _gh_repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", "")


def get_last_update_id() -> int:
    repo = _gh_repo()
    if not repo:
        return 0
    url = f"https://api.github.com/repos/{repo}/actions/variables/{VARIABLE_NAME}"
    try:
        resp = requests.get(url, headers=_gh_headers(), timeout=10)
        if resp.status_code == 200:
            return int(resp.json().get("value", "0"))
    except Exception:
        pass
    return 0


def set_last_update_id(update_id: int):
    repo = _gh_repo()
    if not repo:
        return
    headers = _gh_headers()
    headers["Content-Type"] = "application/json"
    data = {"name": VARIABLE_NAME, "value": str(update_id)}
    url = f"https://api.github.com/repos/{repo}/actions/variables/{VARIABLE_NAME}"

    resp = requests.patch(url, json=data, headers=headers, timeout=10)
    if resp.status_code == 404:
        # Variable doesn't exist yet — create it
        create_url = f"https://api.github.com/repos/{repo}/actions/variables"
        requests.post(create_url, json=data, headers=headers, timeout=10)


# ── Tweet extraction ──────────────────────────────────────────────────────────

def extract_tweets(message_text: str) -> list[str] | None:
    """Extract tweets from the TWEETS_JSON: line in the original bot message."""
    match = re.search(r'TWEETS_JSON:(.+)$', message_text, re.MULTILINE)
    if not match:
        return None
    try:
        return json.loads(match.group(1).strip())
    except json.JSONDecodeError:
        return None


# ── X posting ─────────────────────────────────────────────────────────────────

def post_to_x(tweets: list[str]) -> str:
    """Posts tweet(s) to X. Returns the first tweet ID."""
    from engine.x_poster import post_thread, post_single
    if len(tweets) == 1:
        return post_single(tweets[0])
    else:
        ids = post_thread(tweets)
        return ids[0]


# ── Main logic ────────────────────────────────────────────────────────────────

def main():
    last_id = get_last_update_id()
    print(f"[approvals] Last processed update_id: {last_id}")

    updates = get_updates(offset=last_id + 1)
    print(f"[approvals] New updates: {len(updates)}")

    if not updates:
        print("[approvals] Nothing to process.")
        return

    max_id = last_id
    processed = 0
    errors = 0

    for update in updates:
        uid = update.get("update_id", 0)
        if uid > max_id:
            max_id = uid

        msg = update.get("message")
        if not msg:
            continue

        # Only process messages from the authorised chat
        chat_id = str(msg.get("chat", {}).get("id", ""))
        if chat_id != _tg_chat_id():
            continue

        # Must be a reply to one of our bot messages
        reply_to = msg.get("reply_to_message")
        if not reply_to:
            continue

        text = msg.get("text", "").strip().lower()
        original_text = reply_to.get("text", "")

        tweets = extract_tweets(original_text)

        if text in YES_WORDS:
            if not tweets:
                send_telegram(
                    "⚠️ Could not find tweet content in the original message. "
                    "Make sure you reply directly to the post notification."
                )
                continue

            print(f"[approvals] Posting {len(tweets)} tweet(s) to X...")
            try:
                tweet_id = post_to_x(tweets)
                url = f"https://x.com/FortuneAndRuin/status/{tweet_id}"
                send_telegram(f"✅ Posted to X!\n{url}")
                print(f"[approvals] Posted: {url}")
                processed += 1
            except Exception as e:
                send_telegram(f"❌ Failed to post to X: {e}")
                print(f"[approvals] X post error: {e}")
                errors += 1

        elif text in NO_WORDS:
            send_telegram("🗑️ Post skipped.")
            print("[approvals] Post rejected by user.")
            processed += 1

    # Always advance the offset so we don't reprocess
    if max_id > last_id:
        set_last_update_id(max_id)
        print(f"[approvals] Updated last_update_id to {max_id}")

    print(f"[approvals] Done. Processed={processed}, Errors={errors}")


if __name__ == "__main__":
    main()

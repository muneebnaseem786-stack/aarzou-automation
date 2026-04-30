"""Entry point for the reaction radar GitHub Actions job (runs every 2 hours)."""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.content.trend_scanner import collect_all_articles
from scripts.content.reaction_generator import generate_reaction_posts

QUEUE_PATH = "data/reaction_queue.json"
MAX_QUEUE_SIZE = 40


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to GitHub Secrets.")
        sys.exit(1)

    print("=== Reaction Radar Job ===")
    print("Step 1: Collecting recent articles (last 4 hours)...")
    articles = collect_all_articles(from_hours=4)
    print(f"  Found {len(articles)} articles")

    print("Step 2: Generating reaction posts...")
    new_posts = generate_reaction_posts(articles)
    print(f"  Generated {len(new_posts)} reaction posts")

    if not new_posts:
        print("  Nothing interesting to react to this run.")

    os.makedirs("data", exist_ok=True)
    try:
        with open(QUEUE_PATH) as f:
            existing = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        existing = {"posts": []}

    all_posts = new_posts + existing.get("posts", [])
    all_posts = all_posts[:MAX_QUEUE_SIZE]

    with open(QUEUE_PATH, "w") as f:
        json.dump({
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "posts": all_posts,
        }, f, indent=2)

    pending = sum(1 for p in all_posts if p.get("status") == "pending")
    print(f"Queue: {len(all_posts)} total, {pending} pending approval")


if __name__ == "__main__":
    main()

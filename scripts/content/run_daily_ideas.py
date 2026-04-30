"""Entry point for the daily ideas GitHub Actions job."""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.content.trend_scanner import collect_all_articles
from scripts.content.content_generator import generate_ideas, generate_full_pack


def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY not set. Add it to GitHub Secrets.")
        sys.exit(1)

    print("=== Daily Ideas Job ===")
    print("Step 1: Collecting articles...")
    articles = collect_all_articles(from_hours=24)
    print(f"  Found {len(articles)} relevant articles")

    print("Step 2: Generating content ideas...")
    ideas = generate_ideas(articles)
    print(f"  Generated {len(ideas)} ideas")

    print("Step 3: Generating full content packs...")
    for i, idea in enumerate(ideas):
        print(f"  Pack {i+1}/{len(ideas)}: {idea.get('title', '')[:50]}")
        idea["content_pack"] = generate_full_pack(idea)

    os.makedirs("data", exist_ok=True)
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "article_count": len(articles),
        "ideas": ideas,
    }
    with open("data/content_ideas.json", "w") as f:
        json.dump(output, f, indent=2)

    print(f"Done. Saved {len(ideas)} ideas with full packs to data/content_ideas.json")


if __name__ == "__main__":
    main()

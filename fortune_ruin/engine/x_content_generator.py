import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from .claude_client import load_prompt, call_claude_json
from .x_hook_jury import get_best_hook
from db.database import get_posted_x_topics, init_db

init_db()  # ensures posted_x_content table exists

POST_TYPES = [
    "financial_history_thread",
    "hot_take",
    "behind_the_scenes",
    "video_promotion",
]


def generate_x_post(post_type: str, context: str) -> dict:
    """
    Full pipeline:
      1. Run hook jury → get the strongest hook
      2. Generate the full thread with the approved hook as tweet 1
    Returns { post_type, tweets: [{ tweet_number, content, is_thread_continuation }] }
    """
    if post_type not in POST_TYPES:
        raise ValueError(f"Unknown post_type '{post_type}'. Must be one of: {POST_TYPES}")

    # Step 1: hook jury
    approved_hook = get_best_hook(post_type, context)

    # Step 2: generate thread
    covered = get_posted_x_topics()
    covered_str = ", ".join(covered[:30]) if covered else "None yet"

    prompt_template = load_prompt("x_post_prompt")
    prompt = prompt_template.format(
        post_type=post_type,
        context=context,
        approved_hook=approved_hook,
        covered_topics=covered_str,
    )
    result = call_claude_json(prompt, max_tokens=2000)

    if "tweets" not in result:
        raise ValueError(f"Missing 'tweets' key in response: {result.keys()}")

    # Enforce tweet 1 = approved hook, enforce 280 char limit
    tweets = result["tweets"]
    if tweets:
        tweets[0]["content"] = approved_hook

    for tweet in tweets:
        if len(tweet["content"]) > 280:
            tweet["content"] = tweet["content"][:277].rsplit(" ", 1)[0] + "..."

    return result


def generate_weekly_batch(
    current_topic: str | None = None,
    current_script_excerpt: str | None = None,
    video_title: str | None = None,
    video_key_insight: str | None = None,
    current_news: str | None = None,
) -> list[dict]:
    """Generate a balanced weekly batch of X posts."""
    batch = []

    for i in range(2):
        ctx = (
            "Pick a compelling financial history event or figure that illustrates the "
            "'beneficiary framing' — who profited from a system that harmed others. "
            "Must work as a standalone viral thread with no video context."
        )
        if current_topic:
            ctx += f" Avoid the topic we're currently producing: {current_topic}."
        batch.append(generate_x_post("financial_history_thread", ctx))

    if current_news:
        batch.append(generate_x_post("hot_take", current_news))
    else:
        ctx = "Pick a current financial or economic phenomenon and connect it to a historical parallel using the Fortune & Ruin forensic lens."
        batch.append(generate_x_post("hot_take", ctx))

    if current_topic:
        ctx = f"We are currently researching: {current_topic}."
        if current_script_excerpt:
            ctx += f" Striking excerpt: {current_script_excerpt[:500]}"
        batch.append(generate_x_post("behind_the_scenes", ctx))

    if video_title and video_key_insight:
        ctx = f"Video title: {video_title}\nKey insight: {video_key_insight}"
        batch.append(generate_x_post("video_promotion", ctx))

    return batch

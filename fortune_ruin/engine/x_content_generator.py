from .claude_client import load_prompt, call_claude_json

POST_TYPES = [
    "financial_history_thread",
    "hot_take",
    "behind_the_scenes",
    "video_promotion",
]


def generate_x_post(post_type: str, context: str) -> dict:
    """
    Returns { post_type, tweets: [{ tweet_number, content, is_thread_continuation }] }
    """
    if post_type not in POST_TYPES:
        raise ValueError(f"Unknown post_type '{post_type}'. Must be one of: {POST_TYPES}")

    prompt_template = load_prompt("x_post_prompt")
    prompt = prompt_template.format(post_type=post_type, context=context)
    result = call_claude_json(prompt, max_tokens=2000)

    if "tweets" not in result:
        raise ValueError(f"Missing 'tweets' key in X post response: {result.keys()}")

    for tweet in result["tweets"]:
        if len(tweet["content"]) > 280:
            # Truncate gracefully at last space before 280
            tweet["content"] = tweet["content"][:277].rsplit(" ", 1)[0] + "..."

    return result


def generate_weekly_batch(
    current_topic: str | None = None,
    current_script_excerpt: str | None = None,
    video_title: str | None = None,
    video_key_insight: str | None = None,
    current_news: str | None = None,
) -> list[dict]:
    """
    Generate a balanced weekly batch of X posts across content types.
    Returns a list of post dicts ready for the review queue.
    """
    batch = []

    # 2x standalone financial history threads (backbone of account building)
    for i in range(2):
        ctx = f"Topic idea {i+1} for a standalone financial history thread in the Fortune & Ruin niche. "
        ctx += "Pick a compelling financial history event or figure that illustrates the 'beneficiary framing' — who profited from a system that harmed others. "
        if current_topic:
            ctx += f"Avoid the topic we're currently producing: {current_topic}."
        post = generate_x_post("financial_history_thread", ctx)
        batch.append(post)

    # 1x hot take on current news (if news context provided)
    if current_news:
        post = generate_x_post("hot_take", current_news)
        batch.append(post)
    else:
        ctx = "Pick a current financial or economic phenomenon and connect it to a historical parallel using the Fortune & Ruin forensic lens."
        post = generate_x_post("hot_take", ctx)
        batch.append(post)

    # 1x behind the scenes (if in active production)
    if current_topic:
        ctx = f"We are currently researching and writing an episode about: {current_topic}."
        if current_script_excerpt:
            ctx += f" Here is a striking excerpt from the research: {current_script_excerpt[:500]}"
        post = generate_x_post("behind_the_scenes", ctx)
        batch.append(post)

    # 1x video promotion thread (if a video is being published)
    if video_title and video_key_insight:
        ctx = f"Video title: {video_title}\nKey insight from the video: {video_key_insight}"
        post = generate_x_post("video_promotion", ctx)
        batch.append(post)

    return batch

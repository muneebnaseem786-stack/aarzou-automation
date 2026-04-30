"""
Idea Generation Engine — Fortune & Ruin

Sources:
  1. Reddit (PRAW, read-only anonymous) — top posts from finance/history subreddits
  2. YouTube Data API v3 — trending/high-performing videos in the niche
  3. Claude — synthesises signals into ranked F&R episode ideas

Required env vars:
  REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET  — Reddit script app (read-only)
  YOUTUBE_API_KEY                          — Google Cloud, YouTube Data API v3
  ANTHROPIC_API_KEY                        — already used elsewhere
"""

import os
import requests
from .claude_client import load_prompt, call_claude_json

# ── CONSTANTS ─────────────────────────────────────────────────────────────────

REDDIT_SUBREDDITS = [
    "economics", "finance", "history", "geopolitics",
    "MacroEconomics", "collapse",
]

YOUTUBE_SEARCH_TERMS = [
    "financial history documentary",
    "economic collapse history",
    "banking scandal history",
    "historical financial crisis",
    "who profited from",
    "financial crime history",
]

COMPETITOR_CHANNEL_IDS = [
    "UCIvlODq2MkqMOIc5apBn5dw",  # Financial Historian (approx — verify)
    "UCGy4ztBT_sTEpH1gaxILK8g",  # MagnatesMedia
    "UCBcRF18a7Qf58cCRy5xuWwQ",  # Business Casual
]

COVERED_TOPICS = [
    "Jekyll Island 1910 / Fed founding",
    "Rockefeller / Standard Oil / Gilded Age",
    "Spanish Empire / Price Revolution / silver debasement",
    "Operation Bernhard / WWII counterfeiting",
    "City of London / financial sovereignty",
    "Iran shadow economy / IRGC",
    "BIS / supranational banking / Basel",
    "Dollar reserve status / petrodollar / de-dollarization",
    "Japan 1989 bubble / Nikkei / Plaza Accord",
    "South Sea Company 1720 / Isaac Newton",
    "FDR Executive Order 6102 / 1933 gold seizure",
    "British colonial drain / EIC / home charges",
    "2008 crash mechanics / Lehman / Goldman",
    "Jakob Fugger / Holy Roman Emperor",
]

TIER1_BACKLOG = [
    "Richard Cantillon / The Cantillon Effect",
    "JP Morgan WWI loan 1915",
    "John Law and the Mississippi Bubble 1720",
    "The 1946 Anglo-American Loan",
    "The Swiss Banking Secrecy Act 1934",
]


# ── REDDIT FETCHER ────────────────────────────────────────────────────────────

def _fetch_reddit_signals() -> str:
    """
    Fetch top posts from subreddits using Reddit's public JSON API.
    No credentials required for read-only public data.
    Falls back to PRAW if env vars are set.
    """
    posts = []
    headers = {"User-Agent": "FortuneAndRuin/1.0 ResearchBot (read-only)"}

    for sub in REDDIT_SUBREDDITS:
        try:
            url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit=10"
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            data = resp.json()
            for post in data.get("data", {}).get("children", []):
                p = post["data"]
                if p.get("score", 0) < 50:
                    continue
                posts.append(
                    f"r/{sub} | {p['score']} upvotes | {p['title']}"
                )
        except Exception:
            continue

    if not posts:
        return "Reddit: No data retrieved (check network or credentials)."

    return "\n".join(posts[:60])  # Cap at 60 posts to stay within token budget


# ── YOUTUBE FETCHER ───────────────────────────────────────────────────────────

def _fetch_youtube_signals() -> str:
    """
    Search YouTube Data API v3 for top videos in the F&R niche.
    Also fetches recent uploads from competitor channels.
    Falls back to a graceful message if API key not set.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return "YouTube: YOUTUBE_API_KEY not set — skipping YouTube signals."

    results = []
    base = "https://www.googleapis.com/youtube/v3"

    # Search for top videos in niche (last 90 days)
    for term in YOUTUBE_SEARCH_TERMS[:4]:  # Limit API quota usage
        try:
            resp = requests.get(
                f"{base}/search",
                params={
                    "part": "snippet",
                    "q": term,
                    "type": "video",
                    "order": "viewCount",
                    "publishedAfter": _days_ago_iso(90),
                    "maxResults": 8,
                    "videoDuration": "long",
                    "key": api_key,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            items = resp.json().get("items", [])
            video_ids = [i["id"]["videoId"] for i in items]
            if not video_ids:
                continue

            # Get view counts
            stats_resp = requests.get(
                f"{base}/videos",
                params={
                    "part": "statistics,snippet",
                    "id": ",".join(video_ids),
                    "key": api_key,
                },
                timeout=10,
            )
            if stats_resp.status_code != 200:
                continue
            for v in stats_resp.json().get("items", []):
                title = v["snippet"]["title"]
                channel = v["snippet"]["channelTitle"]
                views = int(v["statistics"].get("viewCount", 0))
                pub = v["snippet"]["publishedAt"][:10]
                results.append(
                    f'"{title}" — {channel} | {views:,} views | published {pub} | search: "{term}"'
                )
        except Exception:
            continue

    # Fetch recent uploads from competitor channels (outlier detection)
    for channel_id in COMPETITOR_CHANNEL_IDS:
        try:
            resp = requests.get(
                f"{base}/search",
                params={
                    "part": "snippet",
                    "channelId": channel_id,
                    "type": "video",
                    "order": "viewCount",
                    "publishedAfter": _days_ago_iso(60),
                    "maxResults": 5,
                    "key": api_key,
                },
                timeout=10,
            )
            if resp.status_code != 200:
                continue
            items = resp.json().get("items", [])
            video_ids = [i["id"]["videoId"] for i in items]
            if not video_ids:
                continue

            stats_resp = requests.get(
                f"{base}/videos",
                params={
                    "part": "statistics,snippet",
                    "id": ",".join(video_ids),
                    "key": api_key,
                },
                timeout=10,
            )
            if stats_resp.status_code != 200:
                continue
            for v in stats_resp.json().get("items", []):
                title = v["snippet"]["title"]
                channel = v["snippet"]["channelTitle"]
                views = int(v["statistics"].get("viewCount", 0))
                pub = v["snippet"]["publishedAt"][:10]
                results.append(
                    f'[COMPETITOR] "{title}" — {channel} | {views:,} views | published {pub}'
                )
        except Exception:
            continue

    if not results:
        return "YouTube: No results retrieved."

    return "\n".join(results[:50])


def _days_ago_iso(days: int) -> str:
    from datetime import datetime, timedelta
    dt = datetime.utcnow() - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT00:00:00Z")


# ── CLAUDE SYNTHESIS ──────────────────────────────────────────────────────────

def _synthesise_ideas(reddit_signals: str, youtube_signals: str) -> list[dict]:
    prompt_template = load_prompt("idea_generator_prompt")
    prompt = prompt_template.format(
        covered_topics="\n".join(f"- {t}" for t in COVERED_TOPICS),
        tier1_backlog="\n".join(f"- {t}" for t in TIER1_BACKLOG),
        reddit_signals=reddit_signals,
        youtube_signals=youtube_signals,
    )
    ideas = call_claude_json(prompt, max_tokens=4000)
    if not isinstance(ideas, list):
        raise ValueError(f"Expected list from idea generator, got: {type(ideas)}")
    return ideas


# ── PUBLIC ENTRY POINT ────────────────────────────────────────────────────────

def generate_ideas(progress_callback=None) -> list[dict]:
    """
    Full idea generation pipeline.
    progress_callback: optional callable(message: str) for UI status updates.

    Returns a list of up to 8 ranked idea dicts.
    """
    def _progress(msg):
        if progress_callback:
            progress_callback(msg)

    _progress("Scanning Reddit — top posts from last 7 days…")
    reddit = _fetch_reddit_signals()

    _progress("Searching YouTube — top videos in niche (last 90 days)…")
    youtube = _fetch_youtube_signals()

    _progress("Synthesising signals with Claude — generating ranked ideas…")
    ideas = _synthesise_ideas(reddit, youtube)

    return ideas

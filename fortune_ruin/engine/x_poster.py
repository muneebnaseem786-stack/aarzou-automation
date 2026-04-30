"""
X (Twitter) poster — posts threads using tweepy v4 OAuth1.
"""

import os
import tweepy
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).parent.parent / ".env")


def get_client() -> tweepy.Client:
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_TOKEN_SECRET"],
    )


def post_thread(tweets: list[str]) -> list[str]:
    """
    Post a list of tweet strings as a thread.
    Returns list of posted tweet IDs.
    """
    client = get_client()
    posted_ids = []
    reply_to = None

    for text in tweets:
        if reply_to:
            resp = client.create_tweet(text=text, in_reply_to_tweet_id=reply_to)
        else:
            resp = client.create_tweet(text=text)
        tweet_id = str(resp.data["id"])
        posted_ids.append(tweet_id)
        reply_to = tweet_id

    return posted_ids


def post_single(text: str) -> str:
    client = get_client()
    resp = client.create_tweet(text=text)
    return str(resp.data["id"])

"""Scans RSS feeds and NewsAPI for trending topics matching content pillars."""

import os
import feedparser
import requests
from datetime import datetime, timedelta, timezone

RSS_FEEDS = [
    ("CoinDesk",      "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("The Block",     "https://www.theblock.co/rss.xml"),
    ("Decrypt",       "https://decrypt.co/feed"),
    ("Reuters Biz",   "https://feeds.reuters.com/reuters/businessNews"),
    ("Arab News",     "https://www.arabnews.com/rss.xml"),
    ("Hacker News",   "https://news.ycombinator.com/rss"),
]

NEWSAPI_QUERIES = [
    "stablecoin USDC Tether payment rails",
    "UAE fintech MENA payments Gulf",
    "SaaS AI enterprise software valuation",
    "private equity software acquisition",
    "Pakistan Middle East diplomacy",
    "fintech regulation crypto payments",
]

PILLAR_KEYWORDS = [
    "stablecoin", "usdc", "tether", "payment", "fintech", "defi",
    "uae", "mena", "saudi", "gulf", "hormuz", "opec",
    "saas", "enterprise", "ai software", "valuation",
    "private equity", "pe fund", "acquisition",
    "pakistan", "diaspora",
]


def _is_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(kw in text for kw in PILLAR_KEYWORDS)


def scan_rss(limit_per_feed: int = 8) -> list[dict]:
    articles = []
    for name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:limit_per_feed]:
                title   = entry.get("title", "")
                summary = entry.get("summary", "")[:400]
                if _is_relevant(title, summary):
                    articles.append({
                        "source":    name,
                        "title":     title,
                        "summary":   summary,
                        "link":      entry.get("link", ""),
                        "published": entry.get("published", ""),
                    })
        except Exception as e:
            print(f"RSS error [{name}]: {e}")
    return articles


def scan_newsapi(from_hours: int = 24) -> list[dict]:
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        print("NEWSAPI_KEY not set — skipping NewsAPI scan")
        return []

    from_date = (datetime.now(timezone.utc) - timedelta(hours=from_hours)).strftime("%Y-%m-%dT%H:%M:%S")
    articles  = []

    for query in NEWSAPI_QUERIES:
        try:
            resp = requests.get(
                "https://newsapi.org/v2/everything",
                params={
                    "q":        query,
                    "from":     from_date,
                    "language": "en",
                    "sortBy":   "relevancy",
                    "pageSize": 5,
                    "apiKey":   api_key,
                },
                timeout=10,
            )
            resp.raise_for_status()
            for a in resp.json().get("articles", []):
                articles.append({
                    "source":    a["source"]["name"],
                    "title":     a["title"] or "",
                    "summary":   (a.get("description") or "")[:400],
                    "link":      a["url"],
                    "published": a["publishedAt"],
                })
        except Exception as e:
            print(f"NewsAPI error [{query[:30]}]: {e}")

    return articles


def collect_all_articles(from_hours: int = 24) -> list[dict]:
    articles = scan_rss() + scan_newsapi(from_hours)

    seen, unique = set(), []
    for a in articles:
        key = a["title"].strip().lower()
        if key and key not in seen:
            seen.add(key)
            unique.append(a)

    print(f"Collected {len(unique)} unique articles")
    return unique

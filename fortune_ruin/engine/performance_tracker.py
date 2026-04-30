"""
Performance Tracker — Fortune & Ruin

Handles:
  1. Parsing YouTube Studio CSV exports
  2. Enriching video records with metadata tags (title formula, hook type, etc.)
  3. Computing derived metrics for the analytics dashboard
"""

import io
import pandas as pd
from pathlib import Path
from db.database import upsert_video, get_all_videos

TITLE_FORMULAS = [
    "Paradox question",
    "Named crime with scale",
    "Hidden truth",
    "Named figure / unexpected outcome",
    "Other",
]

HOOK_TYPES = [
    "in_media_res",
    "counterintuitive",
    "contrast_paradox",
    "specific_number",
    "revelation",
    "unknown",
]

TOPIC_CATEGORIES = [
    "Banking & Central Banks",
    "Colonial & Imperial Finance",
    "Crashes & Bubbles",
    "Currency & Inflation",
    "Geopolitical Finance",
    "Corporate Crime & Fraud",
    "War Finance",
    "Individual Financiers",
    "Other",
]


def parse_youtube_studio_csv(file_bytes: bytes) -> pd.DataFrame:
    """
    Parse a YouTube Studio analytics CSV export.
    YouTube Studio exports use UTF-16 LE encoding with BOM.
    Handles multiple possible column name formats.
    """
    # Try UTF-16 first (YouTube Studio default), fall back to UTF-8
    for encoding in ("utf-16", "utf-8-sig", "utf-8"):
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding)
            break
        except Exception:
            continue
    else:
        raise ValueError("Could not parse CSV — try exporting again from YouTube Studio.")

    # Normalise column names (YouTube Studio varies by region/version)
    df.columns = [c.strip() for c in df.columns]
    col_map = {
        "Video title": "title",
        "Content": "title",
        "Views": "views",
        "Watch time (hours)": "watch_time_hours",
        "Subscribers": "subs_gained",
        "Impressions": "impressions",
        "Impressions click-through rate (%)": "ctr",
        "Impressions click-through rate": "ctr",
        "Average view duration": "avd_raw",
        "Average percentage viewed (%)": "avd_pct",
        "Likes": "likes",
        "Published": "published_at",
        "Video publish time": "published_at",
        "Video ID": "youtube_id",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    # Parse AVD from "MM:SS" or "HH:MM:SS" string to seconds
    if "avd_raw" in df.columns:
        df["avd_seconds"] = df["avd_raw"].apply(_parse_duration_to_seconds)
    elif "avd_seconds" not in df.columns:
        df["avd_seconds"] = 0

    # Clean numeric columns
    for col in ("views", "impressions", "subs_gained", "likes"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce").fillna(0).astype(int)

    for col in ("ctr", "avd_pct", "watch_time_hours"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace("%", ""), errors="coerce").fillna(0.0)

    # Keep only rows with a title
    if "title" in df.columns:
        df = df[df["title"].notna() & (df["title"].str.strip() != "")]

    return df


def _parse_duration_to_seconds(val) -> int:
    if pd.isna(val):
        return 0
    parts = str(val).strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except Exception:
        pass
    return 0


def compute_like_ratio(df: pd.DataFrame) -> pd.DataFrame:
    if "likes" in df.columns and "views" in df.columns:
        df["like_ratio"] = (df["likes"] / df["views"].replace(0, 1) * 100).round(2)
    return df


def import_csv_to_db(df: pd.DataFrame, metadata_map: dict[str, dict] | None = None) -> int:
    """
    Import a parsed YouTube Studio CSV DataFrame into the database.
    metadata_map: optional dict keyed by video title with extra fields
                  (title_formula, hook_type, topic_category, is_short)
    Returns number of records upserted.
    """
    df = compute_like_ratio(df)
    count = 0
    for _, row in df.iterrows():
        title = row.get("title", "").strip()
        if not title:
            continue

        extra = (metadata_map or {}).get(title, {})
        data = {
            "title": title,
            "youtube_id": row.get("youtube_id", None),
            "title_formula": extra.get("title_formula", "Other"),
            "hook_type": extra.get("hook_type", "unknown"),
            "topic_category": extra.get("topic_category", "Other"),
            "published_at": str(row.get("published_at", ""))[:10] or None,
            "is_short": int(extra.get("is_short", 0)),
            "idea_id": extra.get("idea_id", None),
            "views": int(row.get("views", 0)),
            "impressions": int(row.get("impressions", 0)),
            "ctr": float(row.get("ctr", 0.0)),
            "avd_seconds": int(row.get("avd_seconds", 0)),
            "avd_pct": float(row.get("avd_pct", 0.0)),
            "watch_time_hours": float(row.get("watch_time_hours", 0.0)),
            "subs_gained": int(row.get("subs_gained", 0)),
            "likes": int(row.get("likes", 0)),
            "like_ratio": float(row.get("like_ratio", 0.0)),
        }
        upsert_video(data)
        count += 1
    return count


def get_analytics_dataframe() -> pd.DataFrame:
    """Load all videos from DB into a DataFrame for analysis."""
    videos = get_all_videos()
    if not videos:
        return pd.DataFrame()
    df = pd.DataFrame(videos)
    df["published_at"] = pd.to_datetime(df["published_at"], errors="coerce")
    return df


def quadrant_label(row) -> str:
    """Classify video into CTR/AVD quadrant."""
    ctr_med = 3.0   # Threshold for "good" CTR on a new channel
    avd_med = 35.0  # Threshold for "good" AVD percentage
    ctr_ok = row.get("ctr", 0) >= ctr_med
    avd_ok = row.get("avd_pct", 0) >= avd_med
    if ctr_ok and avd_ok:
        return "✅ Push this"
    elif ctr_ok and not avd_ok:
        return "⚠️ Title misleads"
    elif not ctr_ok and avd_ok:
        return "⚠️ Not finding audience"
    else:
        return "❌ Needs rework"

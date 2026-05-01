import sqlite3
import os
from pathlib import Path

DB_PATH = Path(__file__).parent / "fortune_ruin.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.executescript("""
    CREATE TABLE IF NOT EXISTS ideas (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        topic       TEXT NOT NULL,
        fr_angle    TEXT,
        source_signals TEXT,
        keyword_demand  TEXT,
        competition_score TEXT,
        suggested_title TEXT,
        status      TEXT NOT NULL DEFAULT 'generated',
        notes       TEXT,
        created_at  DATETIME DEFAULT (datetime('now')),
        updated_at  DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS hooks (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id             INTEGER NOT NULL REFERENCES ideas(id),
        hook_text           TEXT NOT NULL,
        hook_type           TEXT,
        trap_check          TEXT,
        selected            INTEGER DEFAULT 0,
        aggregate_score     REAL DEFAULT 0,
        jury_verdicts       TEXT,
        jury_ran            INTEGER DEFAULT 0,
        created_at          DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS scripts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id         INTEGER NOT NULL REFERENCES ideas(id),
        hook_id         INTEGER REFERENCES hooks(id),
        full_script     TEXT,
        docx_path       TEXT,
        word_count      INTEGER,
        estimated_mins  REAL,
        status          TEXT DEFAULT 'draft',
        created_at      DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS shorts (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        script_id   INTEGER NOT NULL REFERENCES scripts(id),
        title       TEXT NOT NULL,
        script_text TEXT NOT NULL,
        visual_note TEXT,
        selected    INTEGER DEFAULT 0,
        created_at  DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS upload_packages (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        script_id       INTEGER NOT NULL REFERENCES scripts(id),
        title_option_1  TEXT,
        title_option_2  TEXT,
        title_option_3  TEXT,
        final_title     TEXT,
        description     TEXT,
        tags            TEXT,
        thumbnail_brief TEXT,
        package_path    TEXT,
        created_at      DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS videos (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        idea_id         INTEGER REFERENCES ideas(id),
        title           TEXT NOT NULL,
        youtube_id      TEXT,
        title_formula   TEXT,
        hook_type       TEXT,
        topic_category  TEXT,
        published_at    DATE,
        views           INTEGER DEFAULT 0,
        impressions     INTEGER DEFAULT 0,
        ctr             REAL DEFAULT 0,
        avd_seconds     INTEGER DEFAULT 0,
        avd_pct         REAL DEFAULT 0,
        watch_time_hours REAL DEFAULT 0,
        subs_gained     INTEGER DEFAULT 0,
        likes           INTEGER DEFAULT 0,
        like_ratio      REAL DEFAULT 0,
        traffic_search_pct  REAL DEFAULT 0,
        traffic_browse_pct  REAL DEFAULT 0,
        traffic_shorts_pct  REAL DEFAULT 0,
        traffic_external_pct REAL DEFAULT 0,
        is_short        INTEGER DEFAULT 0,
        last_scraped    DATETIME,
        created_at      DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS x_posts (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id        INTEGER REFERENCES videos(id),
        idea_id         INTEGER REFERENCES ideas(id),
        content         TEXT NOT NULL,
        post_type       TEXT NOT NULL,
        scheduled_at    DATETIME,
        status          TEXT DEFAULT 'draft',
        posted_at       DATETIME,
        x_post_id       TEXT,
        created_at      DATETIME DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS posted_x_content (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        topic       TEXT NOT NULL,
        post_type   TEXT NOT NULL,
        hook        TEXT,
        tweets_json TEXT NOT NULL,
        posted_at   DATETIME DEFAULT (datetime('now'))
    );

    CREATE TRIGGER IF NOT EXISTS ideas_updated_at
        AFTER UPDATE ON ideas
        BEGIN
            UPDATE ideas SET updated_at = datetime('now') WHERE id = NEW.id;
        END;
    """)

    conn.commit()
    conn.close()


def update_idea_status(idea_id: int, status: str):
    conn = get_connection()
    conn.execute("UPDATE ideas SET status = ? WHERE id = ?", (status, idea_id))
    conn.commit()
    conn.close()


def get_ideas_by_status(status: str | None = None):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM ideas WHERE status = ? ORDER BY created_at DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM ideas ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_idea(topic, fr_angle="", source_signals="", keyword_demand="",
                competition_score="", suggested_title="", notes=""):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO ideas
           (topic, fr_angle, source_signals, keyword_demand, competition_score, suggested_title, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (topic, fr_angle, source_signals, keyword_demand, competition_score, suggested_title, notes)
    )
    idea_id = cur.lastrowid
    conn.commit()
    conn.close()
    return idea_id


def insert_hooks(idea_id: int, hooks: list[dict]):
    import json
    conn = get_connection()
    conn.executemany(
        """INSERT INTO hooks
           (idea_id, hook_text, hook_type, trap_check, aggregate_score, jury_verdicts, jury_ran)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(
            idea_id,
            h["hook_text"],
            h.get("hook_type", ""),
            h.get("trap_check", ""),
            h.get("aggregate_score", 0),
            json.dumps(h.get("jury", {})) if h.get("jury") else None,
            1 if h.get("jury") else 0,
        ) for h in hooks]
    )
    conn.commit()
    conn.close()


def get_hooks_for_idea(idea_id: int):
    import json
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM hooks WHERE idea_id = ? ORDER BY aggregate_score DESC, id ASC", (idea_id,)
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        if d.get("jury_verdicts"):
            try:
                d["jury"] = json.loads(d["jury_verdicts"])
            except Exception:
                d["jury"] = {}
        else:
            d["jury"] = {}
        result.append(d)
    return result


def select_hook(hook_id: int):
    conn = get_connection()
    hook = dict(conn.execute("SELECT * FROM hooks WHERE id = ?", (hook_id,)).fetchone())
    conn.execute("UPDATE hooks SET selected = 0 WHERE idea_id = ?", (hook["idea_id"],))
    conn.execute("UPDATE hooks SET selected = 1 WHERE id = ?", (hook_id,))
    conn.commit()
    conn.close()
    return hook


def insert_script(idea_id: int, hook_id: int, full_script: str,
                  docx_path: str, word_count: int, estimated_mins: float):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO scripts (idea_id, hook_id, full_script, docx_path, word_count, estimated_mins, status)
           VALUES (?, ?, ?, ?, ?, ?, 'draft')""",
        (idea_id, hook_id, full_script, docx_path, word_count, estimated_mins)
    )
    script_id = cur.lastrowid
    conn.commit()
    conn.close()
    return script_id


def get_script_for_idea(idea_id: int):
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM scripts WHERE idea_id = ? ORDER BY created_at DESC LIMIT 1", (idea_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def insert_shorts(script_id: int, shorts: list[dict]):
    conn = get_connection()
    conn.executemany(
        "INSERT INTO shorts (script_id, title, script_text, visual_note) VALUES (?, ?, ?, ?)",
        [(script_id, s["title"], s["script_text"], s.get("visual_note", "")) for s in shorts]
    )
    conn.commit()
    conn.close()


def get_shorts_for_script(script_id: int):
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM shorts WHERE script_id = ? ORDER BY id", (script_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_videos():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM videos ORDER BY published_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_video(data: dict):
    conn = get_connection()

    # Determine all valid column names for the videos table
    valid_cols = {row[1] for row in conn.execute("PRAGMA table_info(videos)").fetchall()}
    safe_data = {k: v for k, v in data.items() if k in valid_cols}

    if safe_data.get("youtube_id"):
        existing = conn.execute(
            "SELECT id FROM videos WHERE youtube_id = ?", (safe_data["youtube_id"],)
        ).fetchone()
        if existing:
            fields = [k for k in safe_data if k != "youtube_id"]
            sets = ", ".join(f"{f} = ?" for f in fields)
            vals = [safe_data[f] for f in fields] + [safe_data["youtube_id"]]
            conn.execute(f"UPDATE videos SET {sets} WHERE youtube_id = ?", vals)
            conn.commit()
            conn.close()
            return existing["id"]

    cols = ", ".join(safe_data.keys())
    placeholders = ", ".join("?" for _ in safe_data)
    cur = conn.execute(
        f"INSERT INTO videos ({cols}) VALUES ({placeholders})",
        list(safe_data.values()),
    )
    vid_id = cur.lastrowid
    conn.commit()
    conn.close()
    return vid_id


def get_x_posts(status: str | None = None):
    conn = get_connection()
    if status:
        rows = conn.execute(
            "SELECT * FROM x_posts WHERE status = ? ORDER BY scheduled_at ASC", (status,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM x_posts ORDER BY created_at DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_x_post(content: str, post_type: str, scheduled_at=None,
                  video_id=None, idea_id=None):
    conn = get_connection()
    cur = conn.execute(
        """INSERT INTO x_posts (content, post_type, scheduled_at, video_id, idea_id, status)
           VALUES (?, ?, ?, ?, ?, 'draft')""",
        (content, post_type, scheduled_at, video_id, idea_id)
    )
    post_id = cur.lastrowid
    conn.commit()
    conn.close()
    return post_id


def update_x_post_status(post_id: int, status: str, x_post_id: str = None):
    conn = get_connection()
    if x_post_id:
        conn.execute(
            "UPDATE x_posts SET status = ?, x_post_id = ?, posted_at = datetime('now') WHERE id = ?",
            (status, x_post_id, post_id)
        )
    else:
        conn.execute("UPDATE x_posts SET status = ? WHERE id = ?", (status, post_id))
    conn.commit()
    conn.close()


def log_posted_x_content(topic: str, post_type: str, hook: str, tweets: list[str]):
    """Log a confirmed-posted X thread so we never repeat the topic."""
    import json
    conn = get_connection()
    conn.execute(
        "INSERT INTO posted_x_content (topic, post_type, hook, tweets_json) VALUES (?, ?, ?, ?)",
        (topic, post_type, hook, json.dumps(tweets))
    )
    conn.commit()
    conn.close()


def get_posted_x_topics() -> list[str]:
    """Return list of topics already posted on X, for use in generation prompts."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT topic FROM posted_x_content ORDER BY posted_at DESC"
    ).fetchall()
    conn.close()
    return [r["topic"] for r in rows]


if __name__ == "__main__":
    init_db()
    print(f"Database initialized at {DB_PATH}")

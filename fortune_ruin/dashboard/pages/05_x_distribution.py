import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from datetime import datetime, date, timedelta
from db.database import (
    init_db, get_x_posts, insert_x_post, update_x_post_status,
    get_ideas_by_status,
)
from engine.x_content_generator import generate_x_post, generate_weekly_batch, POST_TYPES
from engine.telegram_notifier import send_post_for_approval, send_batch_for_approval
from engine.x_poster import post_thread, post_single

init_db()

st.set_page_config(page_title="X Distribution · F&R", layout="wide")
st.title("🐦 X Distribution — @FortuneAndRuin")
st.caption("Build the Fortune & Ruin brand on X. Content queue, generation, and scheduling.")

POST_TYPE_LABELS = {
    "financial_history_thread": "📜 Financial History Thread",
    "hot_take": "⚡ Hot Take",
    "behind_the_scenes": "🔬 Behind the Scenes",
    "video_promotion": "🎬 Video Promotion",
}

STATUS_COLORS = {
    "draft": "🔵",
    "approved": "🟢",
    "scheduled": "🟡",
    "posted": "✅",
    "rejected": "🔴",
}


# ── SIDEBAR — ACCOUNT STRATEGY ───────────────────────────────────────────────
with st.sidebar:
    st.markdown("### Account Strategy")
    st.info(
        "**Phase 1 (now):** 80% standalone financial history content, 20% video promotion.\n\n"
        "**Phase 2 (month 3+):** Video threads as main format. Engage with niche accounts.\n\n"
        "**Rule:** Every video gets a thread — not just a link drop.\n\n"
        "**Cadence:** 1–2 posts/day max (500/month free tier)."
    )
    st.markdown("### X API Status")
    st.warning("⏳ X API not yet connected. Posts will queue here for manual posting.")


# ── TABS ──────────────────────────────────────────────────────────────────────
tab_queue, tab_generate, tab_batch = st.tabs(["Post Queue", "Generate Single Post", "Generate Weekly Batch"])


# ─── POST QUEUE ───────────────────────────────────────────────────────────────
with tab_queue:
    st.subheader("Post Queue")

    tg_col, filter_col = st.columns([2, 3])
    with tg_col:
        if st.button("📲 Send all drafts to Telegram", type="primary", use_container_width=True):
            drafts = get_x_posts("draft")
            if not drafts:
                st.info("No draft posts to send.")
            else:
                sent = send_batch_for_approval(drafts)
                for p in drafts:
                    update_x_post_status(p["id"], "approved")
                st.success(f"✅ {sent}/{len(drafts)} posts sent to Telegram. Reply with `<id> yes` to post each one.")
                st.rerun()
    with filter_col:
        filter_status = st.selectbox(
            "Filter by status",
            ["All", "draft", "approved", "scheduled", "posted"],
            index=0,
        )

    posts = get_x_posts(None if filter_status == "All" else filter_status)

    if not posts:
        st.info("No posts yet. Generate content below.")
    else:
        for post in posts:
            try:
                post_data = __import__("json").loads(post["content"])
                tweets = post_data.get("tweets", [])
                post_type = post.get("post_type", "unknown")
            except Exception:
                tweets = [{"content": post["content"], "tweet_number": 1}]
                post_type = post.get("post_type", "unknown")

            with st.container(border=True):
                col_a, col_b, col_c = st.columns([2, 2, 1])
                with col_a:
                    st.markdown(f"**{POST_TYPE_LABELS.get(post_type, post_type)}**")
                    st.caption(f"Created: {post['created_at'][:10]}")
                with col_b:
                    if post.get("scheduled_at"):
                        st.caption(f"📅 Scheduled: {post['scheduled_at'][:10]}")
                with col_c:
                    st.markdown(f"{STATUS_COLORS.get(post['status'], '⚪')} {post['status'].title()}")

                # Show tweets
                for tw in tweets[:3]:  # Preview first 3 tweets
                    st.markdown(f"> {tw['content']}")
                if len(tweets) > 3:
                    st.caption(f"… +{len(tweets) - 3} more tweets in thread")

                # Actions
                if post["status"] == "draft":
                    btn_col1, btn_col2, btn_col3, btn_col4 = st.columns(4)
                    with btn_col1:
                        if st.button("📲 Send to Telegram", key=f"tg_{post['id']}", use_container_width=True):
                            try:
                                content = __import__("json").loads(post["content"])
                                tweets = content.get("tweets", [])
                                ok = send_post_for_approval(post["id"], post["post_type"], tweets)
                                if ok:
                                    update_x_post_status(post["id"], "approved")
                                    st.success("Sent to Telegram — reply with the post ID to approve.")
                                    st.rerun()
                                else:
                                    st.error("Failed to send to Telegram.")
                            except Exception as e:
                                st.error(f"Error: {e}")
                    with btn_col2:
                        if st.button("🚀 Post to X Now", key=f"postx_{post['id']}", use_container_width=True):
                            try:
                                content = __import__("json").loads(post["content"])
                                tweets = [tw["content"] for tw in content.get("tweets", [])]
                                if len(tweets) == 1:
                                    tid = post_single(tweets[0])
                                    tids = [tid]
                                else:
                                    tids = post_thread(tweets)
                                update_x_post_status(post["id"], "posted", tids[0])
                                st.success(f"✅ Posted! https://x.com/FortuneAndRuin/status/{tids[0]}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"X posting failed: {e}")
                    with btn_col3:
                        if st.button("✅ Approve", key=f"approve_{post['id']}", use_container_width=True):
                            update_x_post_status(post["id"], "approved")
                            st.rerun()
                    with btn_col4:
                        if st.button("🗑️ Reject", key=f"reject_{post['id']}", use_container_width=True):
                            update_x_post_status(post["id"], "rejected")
                            st.rerun()

                elif post["status"] == "approved":
                    ap_col1, ap_col2 = st.columns(2)
                    with ap_col1:
                        if st.button("🚀 Post to X Now", key=f"postx_ap_{post['id']}", use_container_width=True, type="primary"):
                            try:
                                content = __import__("json").loads(post["content"])
                                tweets = [tw["content"] for tw in content.get("tweets", [])]
                                if len(tweets) == 1:
                                    tid = post_single(tweets[0])
                                    tids = [tid]
                                else:
                                    tids = post_thread(tweets)
                                update_x_post_status(post["id"], "posted", tids[0])
                                st.success(f"✅ Posted! https://x.com/FortuneAndRuin/status/{tids[0]}")
                                st.rerun()
                            except Exception as e:
                                st.error(f"X posting failed: {e}")
                    with ap_col2:
                        if st.button("✅ Mark as Posted (manual)", key=f"posted_{post['id']}", use_container_width=True):
                            update_x_post_status(post["id"], "posted")
                            st.rerun()


# ─── GENERATE SINGLE POST ─────────────────────────────────────────────────────
with tab_generate:
    st.subheader("Generate a Single Post")

    post_type = st.selectbox(
        "Post type",
        list(POST_TYPE_LABELS.keys()),
        format_func=lambda x: POST_TYPE_LABELS[x],
    )

    context_help = {
        "financial_history_thread": "Describe the historical event or figure, or leave blank to let Claude choose.",
        "hot_take": "Paste a current financial news headline or event to connect to history.",
        "behind_the_scenes": "Describe what you're currently researching or a striking fact you found.",
        "video_promotion": "Paste the video title + one-sentence key insight from the episode.",
    }

    context = st.text_area(
        "Context / Input",
        placeholder=context_help.get(post_type, ""),
        height=100,
    )

    scheduled_for = st.date_input("Schedule for date (optional)", value=None)

    if st.button("✨ Generate Post", type="primary", use_container_width=True):
        if not context.strip() and post_type in ("hot_take", "video_promotion"):
            st.warning("Please provide context for this post type.")
        else:
            with st.spinner("Generating X post…"):
                try:
                    result = generate_x_post(post_type, context or "Generate a compelling post.")
                    import json
                    content_json = json.dumps(result)
                    scheduled_dt = (
                        datetime.combine(scheduled_for, datetime.min.time()).isoformat()
                        if scheduled_for else None
                    )
                    post_id = insert_x_post(
                        content=content_json,
                        post_type=post_type,
                        scheduled_at=scheduled_dt,
                    )
                    st.success(f"✅ Post generated and added to queue (#{post_id})")

                    st.markdown("**Preview:**")
                    for tw in result.get("tweets", []):
                        st.markdown(f"> **{tw['tweet_number']}.** {tw['content']}")
                        char_count = len(tw["content"])
                        color = "🟢" if char_count <= 240 else "🟡" if char_count <= 270 else "🔴"
                        st.caption(f"{color} {char_count}/280 chars")
                except Exception as e:
                    st.error(f"Generation failed: {e}")


# ─── WEEKLY BATCH ─────────────────────────────────────────────────────────────
with tab_batch:
    st.subheader("Generate Weekly Content Batch")
    st.markdown(
        "Generate a full week's worth of X posts in one click. "
        "Includes 2 financial history threads, 1 hot take, and optionally a behind-the-scenes and video promotion thread."
    )

    col1, col2 = st.columns(2)
    with col1:
        current_topic = st.text_input(
            "Current episode topic (optional)",
            placeholder="e.g. Richard Cantillon / The Cantillon Effect",
        )
        current_news = st.text_input(
            "Current financial news to react to (optional)",
            placeholder="e.g. Fed holds rates amid tariff uncertainty, May 2026",
        )
    with col2:
        video_title = st.text_input(
            "New video title (if publishing this week, optional)",
            placeholder="e.g. The Man Who Invented Inflation",
        )
        video_key_insight = st.text_area(
            "Key insight from the video (for promotion thread)",
            placeholder="e.g. Cantillon showed in 1730 that new money doesn't reach everyone equally — those closest to the money printer get rich first, and everyone else pays for it.",
            height=80,
        )
        script_excerpt = st.text_area(
            "Striking excerpt from research (optional, for BTS post)",
            placeholder="Paste a fact, quote, or discovery from current research",
            height=60,
        )

    if st.button("🚀 Generate Weekly Batch", type="primary", use_container_width=True):
        with st.spinner("Generating weekly batch — ~60 seconds…"):
            try:
                import json
                batch = generate_weekly_batch(
                    current_topic=current_topic or None,
                    current_script_excerpt=script_excerpt or None,
                    video_title=video_title or None,
                    video_key_insight=video_key_insight or None,
                    current_news=current_news or None,
                )
                for post in batch:
                    insert_x_post(
                        content=json.dumps(post),
                        post_type=post.get("post_type", "unknown"),
                    )
                st.success(f"✅ {len(batch)} posts added to the queue for review.")
                st.markdown("**Preview:**")
                for post in batch:
                    st.markdown(f"**{POST_TYPE_LABELS.get(post.get('post_type', ''), post.get('post_type', ''))}**")
                    for tw in post.get("tweets", [])[:2]:
                        st.markdown(f"> {tw['content']}")
                    st.divider()
            except Exception as e:
                st.error(f"Batch generation failed: {e}")

    with st.expander("📊 Monthly Usage Tracker"):
        posts_this_month = [
            p for p in get_x_posts("posted")
            if p["posted_at"] and p["posted_at"][:7] == date.today().isoformat()[:7]
        ]
        used = len(posts_this_month)
        remaining = 500 - used
        st.progress(used / 500, text=f"{used}/500 posts used this month")
        st.caption(f"Free tier: 500 posts/month · {remaining} remaining")

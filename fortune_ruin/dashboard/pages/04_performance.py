import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db.database import init_db, get_all_videos, upsert_video
from engine.performance_tracker import (
    parse_youtube_studio_csv, import_csv_to_db, get_analytics_dataframe,
    quadrant_label, TITLE_FORMULAS, HOOK_TYPES, TOPIC_CATEGORIES,
)

init_db()

st.set_page_config(page_title="Performance · F&R", layout="wide")
st.title("📊 Performance Tracker")
st.caption("Learn from every video. CTR × AVD × formula — find what's working.")

tab_dashboard, tab_import, tab_manual = st.tabs(
    ["Analytics Dashboard", "Import from YouTube Studio", "Manual Entry"]
)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — ANALYTICS DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════════
with tab_dashboard:
    df = get_analytics_dataframe()

    if df.empty:
        st.info(
            "No video data yet. Import a YouTube Studio CSV or add videos manually using the other tabs."
        )
    else:
        # ── FILTERS ──────────────────────────────────────────────────────────
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            content_type = st.selectbox(
                "Content type",
                ["All", "Long-form only", "Shorts only"],
            )
        with col_f2:
            formula_filter = st.multiselect(
                "Title formula",
                TITLE_FORMULAS,
                default=[],
                placeholder="All formulas",
            )
        with col_f3:
            category_filter = st.multiselect(
                "Topic category",
                TOPIC_CATEGORIES,
                default=[],
                placeholder="All categories",
            )

        filtered = df.copy()
        if content_type == "Long-form only":
            filtered = filtered[filtered["is_short"] == 0]
        elif content_type == "Shorts only":
            filtered = filtered[filtered["is_short"] == 1]
        if formula_filter:
            filtered = filtered[filtered["title_formula"].isin(formula_filter)]
        if category_filter:
            filtered = filtered[filtered["topic_category"].isin(category_filter)]

        if filtered.empty:
            st.warning("No videos match the selected filters.")
        else:
            # ── SUMMARY METRICS ───────────────────────────────────────────────
            st.markdown("### Channel Overview")
            m1, m2, m3, m4, m5 = st.columns(5)
            with m1:
                st.metric("Videos", len(filtered))
            with m2:
                st.metric("Total views", f"{filtered['views'].sum():,}")
            with m3:
                avg_ctr = filtered["ctr"].mean()
                st.metric("Avg CTR", f"{avg_ctr:.1f}%",
                          delta="Good" if avg_ctr >= 3 else "Below target",
                          delta_color="normal" if avg_ctr >= 3 else "inverse")
            with m4:
                avg_avd = filtered["avd_pct"].mean()
                st.metric("Avg AVD", f"{avg_avd:.0f}%",
                          delta="Good" if avg_avd >= 35 else "Below target",
                          delta_color="normal" if avg_avd >= 35 else "inverse")
            with m5:
                st.metric("Watch time (hrs)", f"{filtered['watch_time_hours'].sum():.0f}")

            st.divider()

            # ── CTR × AVD SCATTER (the money chart) ──────────────────────────
            st.markdown("### CTR × Average View Duration — Quadrant Analysis")
            st.caption(
                "High CTR + High AVD = algorithm pushes it. "
                "High CTR + Low AVD = title misleads. "
                "Low CTR + High AVD = great content, not finding audience. "
                "Low CTR + Low AVD = rework needed."
            )

            scatter_df = filtered[filtered["ctr"] > 0].copy()
            scatter_df["quadrant"] = scatter_df.apply(quadrant_label, axis=1)
            scatter_df["label"] = scatter_df["title"].str[:50] + "…"

            if not scatter_df.empty:
                fig = px.scatter(
                    scatter_df,
                    x="ctr",
                    y="avd_pct",
                    size="views",
                    color="quadrant",
                    hover_name="title",
                    hover_data={"views": True, "ctr": ":.1f", "avd_pct": ":.0f",
                                "title_formula": True, "quadrant": False},
                    color_discrete_map={
                        "✅ Push this": "#22c55e",
                        "⚠️ Title misleads": "#f59e0b",
                        "⚠️ Not finding audience": "#3b82f6",
                        "❌ Needs rework": "#ef4444",
                    },
                    labels={"ctr": "CTR (%)", "avd_pct": "Avg View Duration (%)"},
                    title="",
                    height=450,
                )
                # Reference lines
                fig.add_hline(y=35, line_dash="dash", line_color="gray", opacity=0.4)
                fig.add_vline(x=3, line_dash="dash", line_color="gray", opacity=0.4)
                fig.update_layout(
                    plot_bgcolor="#0e1117",
                    paper_bgcolor="#0e1117",
                    font_color="#fafafa",
                    legend_title_text="Quadrant",
                )
                st.plotly_chart(fig, use_container_width=True)

                # Quadrant summary
                q_counts = scatter_df["quadrant"].value_counts()
                qc1, qc2, qc3, qc4 = st.columns(4)
                for col, (label, color) in zip(
                    [qc1, qc2, qc3, qc4],
                    [("✅ Push this", "#22c55e"), ("⚠️ Title misleads", "#f59e0b"),
                     ("⚠️ Not finding audience", "#3b82f6"), ("❌ Needs rework", "#ef4444")]
                ):
                    with col:
                        st.markdown(
                            f"<div style='border-left: 4px solid {color}; padding-left: 8px;'>"
                            f"<strong>{label}</strong><br/>{q_counts.get(label, 0)} videos"
                            f"</div>",
                            unsafe_allow_html=True,
                        )

            st.divider()

            # ── FORMULA PERFORMANCE ───────────────────────────────────────────
            st.markdown("### Title Formula vs. Performance")
            formula_df = filtered[filtered["title_formula"].notna()].copy()
            if len(formula_df) >= 2:
                agg = formula_df.groupby("title_formula").agg(
                    videos=("title", "count"),
                    avg_views=("views", "mean"),
                    avg_ctr=("ctr", "mean"),
                    avg_avd=("avd_pct", "mean"),
                ).reset_index().sort_values("avg_views", ascending=False)

                fc1, fc2 = st.columns(2)
                with fc1:
                    fig2 = px.bar(
                        agg, x="title_formula", y="avg_views",
                        color="avg_ctr", color_continuous_scale="Viridis",
                        labels={"title_formula": "Formula", "avg_views": "Avg Views", "avg_ctr": "Avg CTR (%)"},
                        title="Avg Views by Title Formula",
                        height=350,
                    )
                    fig2.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#fafafa")
                    st.plotly_chart(fig2, use_container_width=True)
                with fc2:
                    fig3 = px.bar(
                        agg, x="title_formula", y="avg_avd",
                        color="avg_ctr", color_continuous_scale="Plasma",
                        labels={"title_formula": "Formula", "avg_avd": "Avg AVD (%)", "avg_ctr": "Avg CTR (%)"},
                        title="Avg Retention by Title Formula",
                        height=350,
                    )
                    fig3.update_layout(plot_bgcolor="#0e1117", paper_bgcolor="#0e1117", font_color="#fafafa")
                    st.plotly_chart(fig3, use_container_width=True)

            st.divider()

            # ── SHORTS vs LONG-FORM ───────────────────────────────────────────
            st.markdown("### Shorts vs. Long-form")
            type_df = df.copy()
            type_df["type"] = type_df["is_short"].map({0: "Long-form", 1: "Short"})
            type_agg = type_df.groupby("type").agg(
                videos=("title", "count"),
                avg_views=("views", "mean"),
                total_views=("views", "sum"),
                avg_ctr=("ctr", "mean"),
                avg_avd=("avd_pct", "mean"),
                avg_like_ratio=("like_ratio", "mean"),
            ).reset_index()

            if len(type_agg) >= 1:
                sc1, sc2, sc3 = st.columns(3)
                for col, metric, label in [
                    (sc1, "avg_views", "Avg Views"),
                    (sc2, "avg_ctr", "Avg CTR (%)"),
                    (sc3, "avg_avd", "Avg AVD (%)"),
                ]:
                    with col:
                        fig_t = px.bar(
                            type_agg, x="type", y=metric,
                            color="type",
                            color_discrete_map={"Long-form": "#3b82f6", "Short": "#f59e0b"},
                            labels={"type": "", metric: label},
                            title=label, height=280,
                        )
                        fig_t.update_layout(
                            plot_bgcolor="#0e1117", paper_bgcolor="#0e1117",
                            font_color="#fafafa", showlegend=False,
                        )
                        st.plotly_chart(fig_t, use_container_width=True)

            st.divider()

            # ── VIDEO TABLE ───────────────────────────────────────────────────
            st.markdown("### All Videos")
            display_cols = ["title", "published_at", "views", "ctr", "avd_pct",
                            "watch_time_hours", "likes", "title_formula", "topic_category"]
            display_df = filtered[[c for c in display_cols if c in filtered.columns]].copy()
            display_df = display_df.sort_values("views", ascending=False)
            display_df["published_at"] = display_df["published_at"].dt.strftime("%Y-%m-%d").fillna("—")
            display_df.columns = [c.replace("_", " ").title() for c in display_df.columns]
            st.dataframe(display_df, use_container_width=True, hide_index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — IMPORT FROM YOUTUBE STUDIO CSV
# ═══════════════════════════════════════════════════════════════════════════════
with tab_import:
    st.markdown("### Import YouTube Studio Analytics CSV")
    st.markdown(
        "**How to export:**\n"
        "1. Open [YouTube Studio](https://studio.youtube.com) → Analytics\n"
        "2. Set date range → Videos tab\n"
        "3. Click Export → Download CSV\n"
        "4. Upload the file below"
    )

    uploaded = st.file_uploader(
        "Upload YouTube Studio CSV",
        type=["csv"],
        help="Export from YouTube Studio Analytics → Videos tab → Export CSV",
    )

    if uploaded:
        try:
            raw_bytes = uploaded.read()
            df_csv = parse_youtube_studio_csv(raw_bytes)
            st.success(f"✅ Parsed {len(df_csv)} videos from CSV.")

            st.markdown("**Preview (first 10 rows):**")
            preview_cols = [c for c in ["title", "views", "impressions", "ctr", "avd_pct", "avd_seconds", "watch_time_hours", "published_at"] if c in df_csv.columns]
            st.dataframe(df_csv[preview_cols].head(10), use_container_width=True)

            st.divider()
            st.markdown(
                "**Tag videos with metadata** (optional — improves formula/hook analysis).\n"
                "You can skip this and import now — tags can be added later via Manual Entry."
            )

            with st.expander("Tag videos with title formula, hook type, and topic category"):
                metadata_map = {}
                for _, row in df_csv.iterrows():
                    title = row.get("title", "").strip()
                    if not title:
                        continue
                    is_short = len(title) <= 60 and row.get("avd_seconds", 99) <= 65
                    st.markdown(f"**{title[:80]}**")
                    tc1, tc2, tc3, tc4 = st.columns([3, 2, 2, 1])
                    with tc1:
                        formula = st.selectbox("Formula", TITLE_FORMULAS, key=f"formula_{title[:30]}")
                    with tc2:
                        hook = st.selectbox("Hook type", HOOK_TYPES, key=f"hook_{title[:30]}")
                    with tc3:
                        category = st.selectbox("Category", TOPIC_CATEGORIES, key=f"cat_{title[:30]}")
                    with tc4:
                        short = st.checkbox("Short?", value=is_short, key=f"short_{title[:30]}")
                    metadata_map[title] = {
                        "title_formula": formula,
                        "hook_type": hook,
                        "topic_category": category,
                        "is_short": int(short),
                    }

            if st.button("⬆️ Import All to Database", type="primary", use_container_width=True):
                n = import_csv_to_db(df_csv, metadata_map if "metadata_map" in dir() else None)
                st.success(f"✅ {n} videos imported / updated.")
                st.rerun()

        except Exception as e:
            st.error(f"CSV parsing failed: {e}")
            st.caption("Make sure you exported from YouTube Studio Analytics → Videos tab.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MANUAL ENTRY
# ═══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.markdown("### Add / Update a Video Manually")
    st.caption("Use this to add a new video or update metrics for an existing one.")

    existing_videos = get_all_videos()
    titles = ["— New video —"] + [v["title"] for v in existing_videos]
    chosen = st.selectbox("Select existing video or add new", titles)

    prefill = {}
    if chosen != "— New video —":
        prefill = next((v for v in existing_videos if v["title"] == chosen), {})

    with st.form("manual_video"):
        col1, col2 = st.columns(2)
        with col1:
            title = st.text_input("Video title *", value=prefill.get("title", ""))
            youtube_id = st.text_input("YouTube video ID", value=prefill.get("youtube_id", ""),
                                       help="The ID from the YouTube URL: youtube.com/watch?v=THIS_PART")
            published_at = st.date_input("Published date", value=pd.to_datetime(prefill.get("published_at")) if prefill.get("published_at") else None)
            is_short = st.checkbox("Is this a Short?", value=bool(prefill.get("is_short", 0)))
            title_formula = st.selectbox("Title formula used", TITLE_FORMULAS,
                                         index=TITLE_FORMULAS.index(prefill.get("title_formula", "Other")) if prefill.get("title_formula") in TITLE_FORMULAS else 0)
            hook_type = st.selectbox("Hook type used", HOOK_TYPES,
                                     index=HOOK_TYPES.index(prefill.get("hook_type", "unknown")) if prefill.get("hook_type") in HOOK_TYPES else 0)
            topic_category = st.selectbox("Topic category", TOPIC_CATEGORIES,
                                          index=TOPIC_CATEGORIES.index(prefill.get("topic_category", "Other")) if prefill.get("topic_category") in TOPIC_CATEGORIES else 0)
        with col2:
            views = st.number_input("Views", min_value=0, value=int(prefill.get("views", 0)))
            impressions = st.number_input("Impressions", min_value=0, value=int(prefill.get("impressions", 0)))
            ctr = st.number_input("CTR (%)", min_value=0.0, max_value=100.0,
                                  value=float(prefill.get("ctr", 0.0)), step=0.1)
            avd_pct = st.number_input("Avg View Duration (%)", min_value=0.0, max_value=100.0,
                                       value=float(prefill.get("avd_pct", 0.0)), step=0.1)
            avd_seconds = st.number_input("Avg View Duration (seconds)", min_value=0,
                                          value=int(prefill.get("avd_seconds", 0)))
            watch_time_hours = st.number_input("Watch time (hours)", min_value=0.0,
                                               value=float(prefill.get("watch_time_hours", 0.0)), step=0.1)
            subs_gained = st.number_input("Subscribers gained", min_value=0,
                                          value=int(prefill.get("subs_gained", 0)))
            likes = st.number_input("Likes", min_value=0, value=int(prefill.get("likes", 0)))

        st.markdown("**Traffic sources (optional)**")
        tr1, tr2, tr3, tr4 = st.columns(4)
        with tr1:
            search_pct = st.number_input("Search %", 0.0, 100.0, float(prefill.get("traffic_search_pct", 0.0)), 0.1)
        with tr2:
            browse_pct = st.number_input("Browse %", 0.0, 100.0, float(prefill.get("traffic_browse_pct", 0.0)), 0.1)
        with tr3:
            shorts_pct = st.number_input("Shorts %", 0.0, 100.0, float(prefill.get("traffic_shorts_pct", 0.0)), 0.1)
        with tr4:
            ext_pct = st.number_input("External %", 0.0, 100.0, float(prefill.get("traffic_external_pct", 0.0)), 0.1)

        submitted = st.form_submit_button("💾 Save Video", type="primary")
        if submitted:
            if not title.strip():
                st.error("Title is required.")
            else:
                like_ratio = round(likes / max(views, 1) * 100, 2)
                upsert_video({
                    "title": title.strip(),
                    "youtube_id": youtube_id.strip() or None,
                    "title_formula": title_formula,
                    "hook_type": hook_type,
                    "topic_category": topic_category,
                    "published_at": published_at.isoformat() if published_at else None,
                    "is_short": int(is_short),
                    "idea_id": None,
                    "views": views,
                    "impressions": impressions,
                    "ctr": ctr,
                    "avd_seconds": avd_seconds,
                    "avd_pct": avd_pct,
                    "watch_time_hours": watch_time_hours,
                    "subs_gained": subs_gained,
                    "likes": likes,
                    "like_ratio": like_ratio,
                    "traffic_search_pct": search_pct,
                    "traffic_browse_pct": browse_pct,
                    "traffic_shorts_pct": shorts_pct,
                    "traffic_external_pct": ext_pct,
                })
                st.success(f"✅ Saved: **{title}**")
                st.rerun()

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from db.database import (
    get_ideas_by_status, insert_idea, update_idea_status, init_db
)

init_db()

st.set_page_config(page_title="Idea Pipeline · F&R", layout="wide")
st.title("💡 Idea Pipeline")
st.caption("Manage your episode ideas from concept to production.")

# ── COVERED TOPICS (from brain file, used for duplicate detection) ──────────
COVERED_TOPICS = [
    "Jekyll Island / Fed founding", "Rockefeller / Standard Oil",
    "Spanish Empire / Price Revolution", "Operation Bernhard",
    "City of London", "Iran shadow economy", "BIS / Basel",
    "Dollar reserve / petrodollar / de-dollarization",
    "Japan 1989 bubble", "South Sea Company 1720",
    "FDR Executive Order 6102 / 1933 gold seizure",
    "British colonial drain / EIC",
    "2008 crash mechanics",
    "Jakob Fugger / Holy Roman Emperor",
]

STATUS_ORDER = [
    "generated", "selected", "hook_drafted",
    "script_drafted", "upload_ready", "published", "tracked",
]

STATUS_LABELS = {
    "generated": "💡 Generated",
    "selected": "✅ Selected",
    "hook_drafted": "🪝 Hook Drafted",
    "script_drafted": "📝 Script Drafted",
    "upload_ready": "📦 Upload Ready",
    "published": "🎬 Published",
    "tracked": "📊 Tracked",
}

NEXT_STATUS = {
    "generated": "selected",
    "selected": "hook_drafted",
    "hook_drafted": "script_drafted",
    "script_drafted": "upload_ready",
    "upload_ready": "published",
    "published": "tracked",
}


# ── ADD NEW IDEA ─────────────────────────────────────────────────────────────
with st.expander("➕ Add New Idea", expanded=False):
    with st.form("add_idea"):
        col1, col2 = st.columns(2)
        with col1:
            topic = st.text_input("Topic *", placeholder="e.g. Richard Cantillon / The Cantillon Effect")
            fr_angle = st.text_area(
                "F&R Angle (who benefited)",
                placeholder="e.g. Early recipients of new money (nobles, court favourites) enriched before prices rose; common people impoverished as purchasing power fell",
                height=80,
            )
            suggested_title = st.text_input(
                "Suggested Title",
                placeholder="e.g. The Man Who Invented Inflation — And Made Himself Rich Doing It",
            )
        with col2:
            source_signals = st.text_area(
                "Source signals",
                placeholder="e.g. VidIQ: high keyword demand for 'Cantillon Effect', Reddit: trending in r/economics this week",
                height=80,
            )
            keyword_demand = st.text_input("Keyword demand", placeholder="e.g. High (VidIQ score: 82)")
            competition_score = st.text_input("Competition level", placeholder="e.g. Low — no forensic-angle video exists")
            notes = st.text_area("Notes", height=60)

        submitted = st.form_submit_button("Add to Pipeline", type="primary")
        if submitted:
            if not topic.strip():
                st.error("Topic is required.")
            elif any(t.lower() in topic.lower() for t in COVERED_TOPICS):
                st.warning("⚠️ This topic may overlap with already-covered content. Double-check before adding.")
            else:
                idea_id = insert_idea(
                    topic=topic.strip(),
                    fr_angle=fr_angle.strip(),
                    source_signals=source_signals.strip(),
                    keyword_demand=keyword_demand.strip(),
                    competition_score=competition_score.strip(),
                    suggested_title=suggested_title.strip(),
                    notes=notes.strip(),
                )
                st.success(f"✅ Idea #{idea_id} added: **{topic}**")
                st.rerun()


# ── KANBAN VIEW ──────────────────────────────────────────────────────────────
st.divider()
st.subheader("Pipeline")

all_ideas = get_ideas_by_status()

# Group by status
grouped: dict[str, list] = {s: [] for s in STATUS_ORDER}
for idea in all_ideas:
    s = idea["status"]
    if s in grouped:
        grouped[s].append(idea)

# Show active stages (generated → upload_ready) in columns
active_statuses = STATUS_ORDER[:5]
cols = st.columns(len(active_statuses))

for col, status in zip(cols, active_statuses):
    with col:
        ideas_in_col = grouped[status]
        st.markdown(f"**{STATUS_LABELS[status]}** ({len(ideas_in_col)})")
        for idea in ideas_in_col:
            with st.container(border=True):
                st.markdown(f"**{idea['topic']}**")
                if idea.get("suggested_title"):
                    st.caption(f"*{idea['suggested_title']}*")
                if idea.get("fr_angle"):
                    st.markdown(f"🎯 {idea['fr_angle'][:120]}{'…' if len(idea['fr_angle']) > 120 else ''}")
                if idea.get("keyword_demand"):
                    st.caption(f"📈 {idea['keyword_demand']}")
                if idea.get("competition_score"):
                    st.caption(f"🏁 {idea['competition_score']}")

                next_s = NEXT_STATUS.get(status)
                if next_s:
                    if st.button(
                        f"→ Move to {STATUS_LABELS[next_s]}",
                        key=f"advance_{idea['id']}",
                        use_container_width=True,
                    ):
                        update_idea_status(idea["id"], next_s)
                        st.rerun()

                if status == "selected":
                    if st.button(
                        "✍️ Go to Script Studio",
                        key=f"script_{idea['id']}",
                        use_container_width=True,
                    ):
                        st.session_state["active_idea_id"] = idea["id"]
                        st.switch_page("pages/02_script_studio.py")


# ── PUBLISHED & TRACKED ───────────────────────────────────────────────────────
st.divider()
pub_col, track_col = st.columns(2)

with pub_col:
    st.subheader(f"{STATUS_LABELS['published']} ({len(grouped['published'])})")
    for idea in grouped["published"]:
        st.markdown(f"- **{idea['topic']}**")

with track_col:
    st.subheader(f"{STATUS_LABELS['tracked']} ({len(grouped['tracked'])})")
    for idea in grouped["tracked"]:
        st.markdown(f"- **{idea['topic']}**")


# ── COVERED TOPICS REFERENCE ─────────────────────────────────────────────────
with st.expander("📋 Already Covered Topics (do not repeat)", expanded=False):
    for t in COVERED_TOPICS:
        st.markdown(f"- {t}")

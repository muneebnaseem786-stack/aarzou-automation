import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from db.database import (
    init_db, get_ideas_by_status, get_hooks_for_idea, insert_hooks,
    select_hook, update_idea_status, insert_script, get_script_for_idea,
    insert_shorts, get_shorts_for_script,
)
from engine.hook_jury import generate_and_evaluate_hooks
from engine.script_generator import generate_script
from engine.shorts_extractor import extract_shorts

init_db()

st.set_page_config(page_title="Script Studio · F&R", layout="wide")
st.title("✍️ Script Studio")
st.caption("Hook → Script → Shorts — the full episode pipeline.")

HOOK_TYPE_LABELS = {
    "in_media_res": "🎬 In Media Res",
    "counterintuitive": "🔄 Counterintuitive",
    "contrast_paradox": "⚡ Contrast / Paradox",
}


# ── IDEA SELECTOR ─────────────────────────────────────────────────────────────
selected_ideas = get_ideas_by_status("selected") + get_ideas_by_status("hook_drafted") + get_ideas_by_status("script_drafted")

if not selected_ideas:
    st.info("No ideas in production yet. Go to the **Idea Pipeline** and move an idea to 'Selected'.")
    st.stop()

idea_options = {f"#{i['id']} — {i['topic']}": i for i in selected_ideas}

# Pre-select if coming from pipeline page
default_key = None
if "active_idea_id" in st.session_state:
    for k, v in idea_options.items():
        if v["id"] == st.session_state["active_idea_id"]:
            default_key = k
            break

chosen_key = st.selectbox(
    "Select idea to work on",
    list(idea_options.keys()),
    index=list(idea_options.keys()).index(default_key) if default_key else 0,
)
idea = idea_options[chosen_key]

st.divider()
st.subheader(f"📌 {idea['topic']}")
if idea.get("fr_angle"):
    st.markdown(f"**F&R Angle:** {idea['fr_angle']}")

# ═══════════════════════════════════════════════════════════════
# STEP 1 — HOOK GENERATION
# ═══════════════════════════════════════════════════════════════
st.markdown("## Step 1 — Hook")

existing_hooks = get_hooks_for_idea(idea["id"])

JUROR_LABELS = {
    "hook_architect":    "🏗️ Hook Architect",
    "algorithm_analyst": "📊 Algorithm Analyst",
    "audience_advocate": "👥 Audience Advocate",
}
JUROR_DESCRIPTIONS = {
    "hook_architect":    "Technical compliance — universal trap, money rule, specificity, rhythm",
    "algorithm_analyst": "YouTube performance — scroll-stopping power, CTR, retention commitment",
    "audience_advocate": "Viewer experience — credibility, relevance, emotional hook",
}

if not existing_hooks:
    st.info(
        "The jury system generates 5 hook candidates, then runs 3 specialist agents in parallel "
        "to score and rank them. You choose from the top 3. Takes ~45 seconds."
    )
    col_gen, col_info = st.columns([2, 3])
    with col_gen:
        if st.button("🪝 Generate Hooks + Run Jury", type="primary", use_container_width=True):
            with st.spinner("Generating 5 hooks and convening the jury — 3 agents scoring in parallel… (~45 seconds)"):
                try:
                    top3 = generate_and_evaluate_hooks(
                        topic=idea["topic"],
                        fr_angle=idea.get("fr_angle", ""),
                    )
                    insert_hooks(idea["id"], top3)
                    update_idea_status(idea["id"], "hook_drafted")
                    st.success("Jury complete — top 3 hooks ranked and ready.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hook jury failed: {e}")
    with col_info:
        with st.expander("How the jury works"):
            for name, desc in JUROR_DESCRIPTIONS.items():
                st.markdown(f"**{JUROR_LABELS[name]}** — {desc}")
            st.caption("Each juror scores 0–10. Hooks ranked by aggregate (max 30). Top 3 presented to you.")

else:
    selected_hook = next((h for h in existing_hooks if h["selected"]), None)

    if not selected_hook:
        st.markdown("**The jury has spoken. Choose your hook:**")
        st.caption("Ranked by aggregate jury score (highest first). All 3 passed the cut.")

        for rank, hook in enumerate(existing_hooks, 1):
            label = HOOK_TYPE_LABELS.get(hook["hook_type"], hook["hook_type"])
            jury = hook.get("jury", {})
            aggregate = hook.get("aggregate_score", 0)
            max_score = hook.get("max_possible", 30)
            score_pct = int((aggregate / max_score) * 100) if max_score else 0

            rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "🔵")

            with st.container(border=True):
                # Header row
                h_col1, h_col2 = st.columns([4, 1])
                with h_col1:
                    st.markdown(f"### {rank_emoji} Rank #{rank} — {label}")
                with h_col2:
                    st.metric("Jury Score", f"{aggregate:.0f}/30", delta=f"{score_pct}%")

                # Hook text
                st.markdown(hook["hook_text"])
                if hook.get("trap_check"):
                    st.caption(f"🎯 Universal trap check: *{hook['trap_check']}*")

                # Jury breakdown
                if jury:
                    with st.expander("📋 Jury Breakdown", expanded=(rank == 1)):
                        j_cols = st.columns(3)
                        for col, (juror_name, _) in zip(j_cols, JUROR_LABELS.items()):
                            verdict = jury.get(juror_name, {})
                            with col:
                                st.markdown(f"**{JUROR_LABELS[juror_name]}**")
                                st.caption(JUROR_DESCRIPTIONS[juror_name])
                                st.metric("Score", f"{verdict.get('total', 0)}/10")
                                if verdict.get("verdict"):
                                    st.success(f"✅ {verdict['verdict']}")
                                if verdict.get("improvement"):
                                    st.info(f"💡 {verdict['improvement']}")

                # Select button
                if st.button(f"✅ Select This Hook", key=f"select_hook_{hook['id']}", type="primary", use_container_width=True):
                    select_hook(hook["id"])
                    st.success("Hook selected! Proceeding to script generation.")
                    st.rerun()

        st.divider()
        if st.button("🔄 Regenerate — Run Jury Again", use_container_width=True):
            with st.spinner("Regenerating hooks and running jury (~45 seconds)…"):
                try:
                    top3 = generate_and_evaluate_hooks(
                        topic=idea["topic"],
                        fr_angle=idea.get("fr_angle", ""),
                    )
                    insert_hooks(idea["id"], top3)
                    st.success("New jury results ready.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hook jury failed: {e}")

    else:
        label = HOOK_TYPE_LABELS.get(selected_hook["hook_type"], selected_hook["hook_type"])
        aggregate = selected_hook.get("aggregate_score", 0)
        st.success(f"✅ Hook selected: **{label}** — Jury score: **{aggregate:.0f}/30**")
        with st.expander("View selected hook + jury verdicts", expanded=False):
            st.markdown(selected_hook["hook_text"])
            jury = selected_hook.get("jury", {})
            if jury:
                j_cols = st.columns(3)
                for col, (juror_name, _) in zip(j_cols, JUROR_LABELS.items()):
                    verdict = jury.get(juror_name, {})
                    with col:
                        st.markdown(f"**{JUROR_LABELS[juror_name]}**")
                        st.metric("Score", f"{verdict.get('total', 0)}/10")
                        if verdict.get("verdict"):
                            st.caption(verdict["verdict"])
        if st.button("↩️ Change Hook"):
            from db.database import get_connection
            conn = get_connection()
            conn.execute("UPDATE hooks SET selected = 0 WHERE idea_id = ?", (idea["id"],))
            conn.commit()
            conn.close()
            st.rerun()

# ═══════════════════════════════════════════════════════════════
# STEP 2 — SCRIPT GENERATION
# ═══════════════════════════════════════════════════════════════
st.divider()
st.markdown("## Step 2 — Full Script")

selected_hook = next((h for h in existing_hooks if h["selected"]), None) if existing_hooks else None
existing_script = get_script_for_idea(idea["id"])

if not selected_hook:
    st.info("Complete Step 1 first — select a hook before generating the script.")
elif not existing_script:
    st.markdown(
        "The full script will be generated using your approved hook and the F&R voice guide. "
        "**Estimated time: 60–90 seconds.**"
    )
    if st.button("📝 Generate Full Script", type="primary", use_container_width=True):
        with st.spinner("Writing the full episode script — sit tight…"):
            try:
                result = generate_script(
                    topic=idea["topic"],
                    fr_angle=idea.get("fr_angle", ""),
                    approved_hook=selected_hook["hook_text"],
                )
                script_id = insert_script(
                    idea_id=idea["id"],
                    hook_id=selected_hook["id"],
                    full_script=result["full_script"],
                    docx_path=result["docx_path"],
                    word_count=result["word_count"],
                    estimated_mins=result["estimated_mins"],
                )
                update_idea_status(idea["id"], "script_drafted")
                st.success(f"✅ Script generated! {result['word_count']:,} words · ~{result['estimated_mins']} minutes")
                st.rerun()
            except Exception as e:
                st.error(f"Script generation failed: {e}")
else:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Word count", f"{existing_script['word_count']:,}")
    with col2:
        st.metric("Est. runtime", f"{existing_script['estimated_mins']} min")
    with col3:
        docx = Path(existing_script["docx_path"])
        if docx.exists():
            with open(docx, "rb") as f:
                st.download_button(
                    "⬇️ Download Script (.docx)",
                    data=f,
                    file_name=docx.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )

    with st.expander("📄 View Script Text", expanded=False):
        st.text_area(
            "Full script",
            value=existing_script["full_script"],
            height=500,
            disabled=True,
        )

    # ─── STEP 3 — SHORTS EXTRACTION ─────────────────────────────────────────
    st.divider()
    st.markdown("## Step 3 — Shorts Extraction")

    existing_shorts = get_shorts_for_script(existing_script["id"])

    if not existing_shorts:
        st.markdown(
            "Claude will read the full script and identify the 4–5 most compelling moments "
            "that work as standalone 60-second Shorts."
        )
        if st.button("🎬 Extract Shorts Concepts", type="primary", use_container_width=True):
            with st.spinner("Extracting Shorts — ~20 seconds…"):
                try:
                    shorts = extract_shorts(
                        topic=idea["topic"],
                        full_script=existing_script["full_script"],
                    )
                    insert_shorts(existing_script["id"], shorts)
                    st.success(f"✅ {len(shorts)} Shorts extracted!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Shorts extraction failed: {e}")
    else:
        st.success(f"✅ {len(existing_shorts)} Short concepts extracted")
        for i, short in enumerate(existing_shorts, 1):
            with st.container(border=True):
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    st.markdown(f"**Short #{i}: {short['title']}**")
                with col_b:
                    st.caption(f"From: {short.get('source_chapter', '—')}")
                st.markdown(short["script_text"])
                if short.get("visual_note"):
                    st.caption(f"🎨 Visual: {short['visual_note']}")

        st.divider()
        st.markdown("### Next Step")
        st.markdown(
            "Your script and Shorts are ready. "
            "Go to **Upload Package** to generate the title, description, tags, and thumbnail brief."
        )
        if st.button("📦 Go to Upload Package", type="primary"):
            st.session_state["active_idea_id"] = idea["id"]
            st.switch_page("pages/03_upload_package.py")

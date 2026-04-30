import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from db.database import (
    init_db, get_ideas_by_status, get_hooks_for_idea, insert_hooks,
    select_hook, update_idea_status, insert_script, get_script_for_idea,
    insert_shorts, get_shorts_for_script,
)
from engine.hook_generator import generate_hooks
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

if not existing_hooks:
    if st.button("🪝 Generate 3 Hook Options", type="primary", use_container_width=True):
        with st.spinner("Generating hooks — this takes ~20 seconds…"):
            try:
                hooks = generate_hooks(
                    topic=idea["topic"],
                    fr_angle=idea.get("fr_angle", ""),
                )
                insert_hooks(idea["id"], hooks)
                update_idea_status(idea["id"], "hook_drafted")
                st.success("Hooks generated!")
                st.rerun()
            except Exception as e:
                st.error(f"Hook generation failed: {e}")
else:
    selected_hook = next((h for h in existing_hooks if h["selected"]), None)

    if not selected_hook:
        st.markdown("**Choose your hook:**")
        for hook in existing_hooks:
            with st.container(border=True):
                label = HOOK_TYPE_LABELS.get(hook["hook_type"], hook["hook_type"])
                st.markdown(f"**{label}**")
                st.markdown(hook["hook_text"])
                if hook.get("trap_check"):
                    st.caption(f"🎯 Universal trap: {hook['trap_check']}")
                if st.button(f"✅ Select This Hook", key=f"select_hook_{hook['id']}", type="primary"):
                    select_hook(hook["id"])
                    st.success("Hook selected!")
                    st.rerun()

        st.divider()
        if st.button("🔄 Regenerate Hooks", use_container_width=True):
            with st.spinner("Regenerating hooks…"):
                try:
                    hooks = generate_hooks(
                        topic=idea["topic"],
                        fr_angle=idea.get("fr_angle", ""),
                    )
                    insert_hooks(idea["id"], hooks)
                    st.success("New hooks generated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Hook generation failed: {e}")
    else:
        label = HOOK_TYPE_LABELS.get(selected_hook["hook_type"], selected_hook["hook_type"])
        st.success(f"✅ Hook selected: **{label}**")
        with st.expander("View selected hook", expanded=False):
            st.markdown(selected_hook["hook_text"])
            if selected_hook.get("trap_check"):
                st.caption(f"🎯 Universal trap: {selected_hook['trap_check']}")
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

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import streamlit as st
from db.database import init_db, get_ideas_by_status, get_script_for_idea, update_idea_status
from engine.claude_client import call_claude

init_db()

st.set_page_config(page_title="Upload Package · F&R", layout="wide")
st.title("📦 Upload Package")
st.caption("Generate your YouTube-ready title, description, tags, and thumbnail brief.")

# ── TITLE FORMULAS REFERENCE ─────────────────────────────────────────────────
TITLE_FORMULAS = {
    "Paradox question": "[Universal fact everyone accepts]… [Question that implies it makes no sense]",
    "Named crime with scale": "[Named actor] + [crime verb] + [$amount] from [named victim]",
    "Hidden truth": "The [hidden/secret/real] [X] behind [famous event]",
    "Named figure, unexpected outcome": "[Named figure] + [unexpected verb] + [counter-intuitive outcome]",
}

THUMBNAIL_COLORS = {
    "Near-black (default)": "#111111",
    "Deep red (threat/danger)": "#4a0000",
    "Dark gold (empire/dynasty)": "#3a2800",
}


def build_upload_prompt(topic: str, fr_angle: str, script_excerpt: str, suggested_title: str) -> str:
    return f"""You are the upload strategist for Fortune & Ruin, a forensic financial history YouTube channel.

Generate a complete YouTube upload package for this episode.

TOPIC: {topic}
F&R ANGLE: {fr_angle}
SUGGESTED TITLE IDEA: {suggested_title}
SCRIPT OPENING (for context):
{script_excerpt[:1200]}

TITLE FORMULAS USED BY F&R (use one per option):
1. Paradox question: [Universal fact]… [Question that implies it makes no sense]
   Example: "Spain Had Infinite Silver and It Destroyed Them"
2. Named crime with scale: [Named actor] + [crime verb] + [$X] from [named victim]
   Example: "How Britain Stole $45 Trillion from India"
3. Hidden truth: The [hidden/secret/real] [X] behind [famous event]
   Example: "The Secret Meeting That Created The US Federal Reserve"
4. Named figure, unexpected outcome: [Named figure] + [unexpected verb] + [counter-intuitive outcome]
   Example: "The Robber Barons: How Losing Made Them Richer"

TITLE RULES:
- Under 60 characters (mobile truncates at ~55)
- Primary keyword in first 4 words where possible
- NO subtitle extensions that over-explain ("— The Colonial Drain" adds no value)
- NO numbered lists ("5 ways...")
- NO question-only titles without specificity

OUTPUT FORMAT — return exactly this structure:

TITLE_1: [option using formula 1 or 2]
TITLE_2: [option using formula 3 or 4]
TITLE_3: [strongest option — your recommended pick]

DESCRIPTION:
[Line 1: hook sentence with primary keyword]
[Line 2: what the video proves — the counterintuitive revelation]
[Line 3: "Subscribe to Fortune & Ruin for more forensic financial history."]

[CHAPTERS PLACEHOLDER — editor will fill timestamps]
0:00 Introduction
[chapters to be added after final edit]

[Subscribe link placeholder]

Sources and further reading:
[3-5 relevant source types the editor should cite — do not fabricate specific URLs]

Follow Fortune & Ruin on X: @FortuneAndRuin

TAGS: [12-15 tags, comma-separated. Primary keyword first, then variations, then broad category tags]

THUMBNAIL_BRIEF:
Background: [near-black / deep red / dark gold — pick based on topic tone]
Text: [2-4 words — the emotional verdict, NOT the title. E.g. if title = named crime → thumbnail = moral verdict]
Text color: Yellow/gold
Visual element: [one face or one symbol — describe specifically]
Contrast note: [how thumbnail text differs from and complements the title]
"""


# ── IDEA SELECTOR ─────────────────────────────────────────────────────────────
ideas = (
    get_ideas_by_status("script_drafted")
    + get_ideas_by_status("upload_ready")
    + get_ideas_by_status("selected")
)

if not ideas:
    st.info("No scripts ready yet. Complete the Script Studio first.")
    st.stop()

idea_options = {f"#{i['id']} — {i['topic']}": i for i in ideas}
default_key = None
if "active_idea_id" in st.session_state:
    for k, v in idea_options.items():
        if v["id"] == st.session_state["active_idea_id"]:
            default_key = k
            break

chosen_key = st.selectbox("Select episode", list(idea_options.keys()),
                           index=list(idea_options.keys()).index(default_key) if default_key else 0)
idea = idea_options[chosen_key]
script = get_script_for_idea(idea["id"])

if not script:
    st.warning("No script found for this idea. Go to Script Studio first.")
    st.stop()

st.divider()
st.subheader(f"📌 {idea['topic']}")

# ── GENERATE PACKAGE ─────────────────────────────────────────────────────────
session_key = f"upload_pkg_{idea['id']}"

if session_key not in st.session_state:
    if st.button("⚙️ Generate Upload Package", type="primary", use_container_width=True):
        with st.spinner("Building upload package — ~30 seconds…"):
            try:
                prompt = build_upload_prompt(
                    topic=idea["topic"],
                    fr_angle=idea.get("fr_angle", ""),
                    script_excerpt=script["full_script"],
                    suggested_title=idea.get("suggested_title", ""),
                )
                raw = call_claude(prompt, max_tokens=2000)
                st.session_state[session_key] = raw
                st.rerun()
            except Exception as e:
                st.error(f"Package generation failed: {e}")
else:
    raw = st.session_state[session_key]

    # Parse sections
    def extract_section(text: str, key: str, end_keys: list[str]) -> str:
        start = text.find(f"{key}:")
        if start == -1:
            return ""
        start += len(f"{key}:")
        end = len(text)
        for ek in end_keys:
            pos = text.find(f"\n{ek}:", start)
            if pos != -1 and pos < end:
                end = pos
        return text[start:end].strip()

    sections = ["TITLE_1", "TITLE_2", "TITLE_3", "DESCRIPTION", "TAGS", "THUMBNAIL_BRIEF"]

    title1 = extract_section(raw, "TITLE_1", sections[1:])
    title2 = extract_section(raw, "TITLE_2", sections[2:])
    title3 = extract_section(raw, "TITLE_3", sections[3:])
    description = extract_section(raw, "DESCRIPTION", sections[4:])
    tags = extract_section(raw, "TAGS", sections[5:])
    thumbnail = extract_section(raw, "THUMBNAIL_BRIEF", [])

    tab1, tab2, tab3, tab4 = st.tabs(["Titles", "Description", "Tags", "Thumbnail Brief"])

    with tab1:
        st.markdown("### Title Options")
        for label, title in [("Option A", title1), ("Option B", title2), ("Option C ⭐ Recommended", title3)]:
            with st.container(border=True):
                col_a, col_b = st.columns([4, 1])
                with col_a:
                    st.markdown(f"**{label}**")
                    st.markdown(f"`{title}`")
                    char_count = len(title)
                    color = "🟢" if char_count <= 55 else "🟡" if char_count <= 70 else "🔴"
                    st.caption(f"{color} {char_count} characters")
                with col_b:
                    st.code(title, language=None)

    with tab2:
        st.markdown("### YouTube Description")
        edited_desc = st.text_area("Edit before copying", value=description, height=300)
        st.caption("Add chapter timestamps after your final video edit.")

    with tab3:
        st.markdown("### Tags")
        edited_tags = st.text_area("Edit tags", value=tags, height=120)
        tag_list = [t.strip() for t in edited_tags.split(",") if t.strip()]
        st.caption(f"{len(tag_list)} tags · YouTube recommends 10–15")

    with tab4:
        st.markdown("### Thumbnail Brief")
        st.markdown(thumbnail)
        st.info("Use this brief in Canva. Dark background, yellow/gold text, 2-4 words max.")

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 Regenerate Package", use_container_width=True):
            del st.session_state[session_key]
            st.rerun()
    with col2:
        if st.button("✅ Mark as Upload Ready", type="primary", use_container_width=True):
            update_idea_status(idea["id"], "upload_ready")
            st.success("Idea marked as Upload Ready!")

    # Title formulas reference
    with st.expander("📚 Title Formula Reference"):
        for name, formula in TITLE_FORMULAS.items():
            st.markdown(f"**{name}:** {formula}")

import sys
from pathlib import Path

# Make parent importable so engine/db modules resolve correctly
sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from db.database import init_db

st.set_page_config(
    page_title="Fortune & Ruin — Production Engine",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Ensure DB exists on every cold start
init_db()

st.title("Fortune & Ruin — Production Engine")
st.markdown(
    "*Autopsy of history's greatest financial events — the full pipeline from idea to upload.*"
)

st.divider()

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.page_link("pages/01_idea_pipeline.py", label="Idea Pipeline", icon="💡")
with col2:
    st.page_link("pages/02_script_studio.py", label="Script Studio", icon="✍️")
with col3:
    st.page_link("pages/03_upload_package.py", label="Upload Package", icon="📦")
with col4:
    st.page_link("pages/05_x_distribution.py", label="X Distribution", icon="🐦")

st.divider()
st.caption("Fortune & Ruin Automation Engine · Phase 1")

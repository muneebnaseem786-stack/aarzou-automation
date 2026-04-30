@echo off
echo Starting Fortune ^& Ruin Production Engine...
cd /d "%~dp0"
set PYTHONPATH=%~dp0
streamlit run dashboard\app.py --server.port 8502

@echo off
echo Starting Fortune ^& Ruin Production Engine...
cd /d "%~dp0"
set PYTHONPATH=%~dp0

echo Starting Telegram approval bot...
start "F&R Telegram Bot" python -m engine.telegram_bot

echo Starting dashboard...
python -m streamlit run dashboard\app.py --server.port 8502 --browser.gatherUsageStats false
pause

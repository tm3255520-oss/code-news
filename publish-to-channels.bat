@echo off
REM Upload DSH video to WeChat Channels draft box (save-only, human confirms publish).
REM Uses existing Hermes publish_channels.py. Needs host BSK + Channels login.
chcp 65001 >nul
"C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe" "C:\Users\Administrator\Documents\code-news\scripts\publish_to_channels.py"
echo.
pause

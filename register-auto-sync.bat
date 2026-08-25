@echo off
echo ============================================
echo  Register AUTO vault sync (every 10 min)
echo  One-time setup - then it runs by itself
echo ============================================
"C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe" "C:\Users\Administrator\.hermes\scripts\register_vault_sync_cron.py"
echo.
echo Done. Auto sync is now registered.
pause

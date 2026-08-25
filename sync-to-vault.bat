@echo off
chcp 65001 >nul
echo ============================================
echo  Sync "pending-vault" files into Obsidian
echo  (待同步vault - 内容生产/热点监控 等白名单)
echo ============================================
"C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe" "C:\Users\Administrator\Documents\code-news\scripts\sync_to_vault.py"
echo.
echo Done. Files are now in Obsidian vault.
pause

@echo off
setlocal
REM ============================================================
REM  register-toolkit.bat (ASCII only)
REM  Registers the unified toolkit-mcp into Codex / Claude Code /
REM  Hermes / DSH MCP configs, then verifies. Run on the HOST.
REM ============================================================
set PY=C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe
set ROOT=C:\Users\Administrator\Documents\code-news
cd /d "%ROOT%"

echo [1/2] Registering toolkit-mcp into agent configs...
"%PY%" scripts\sync_agent_mcp.py
if errorlevel 1 (
  echo ERR: sync_agent_mcp failed.
  pause
  exit /b 1
)

echo [2/2] Verifying...
"%PY%" scripts\sync_agent_mcp.py --verify
"%PY%" scripts\mcp_toolkit_server.py --selftest

echo.
echo DONE. If status lines show MISS for any agent, edit that config manually.
echo Restart Claude Code / Hermes / DSH for the new MCP to take effect.
echo.
pause

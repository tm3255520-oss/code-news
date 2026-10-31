@echo off
REM ============================================================
REM  Card video line (video-line) self check
REM  Double-click to run. ASCII only on purpose (avoids mojibake).
REM  1) regression tests  2) adapter check on the 8-shot storyboard
REM ============================================================
cd /d "%~dp0"
echo === [1/2] regression gate ==============================
python -m unittest tests.scripts.test_card_video_line
if errorlevel 1 (echo [1/2] regression gate: FAIL) else (echo [1/2] regression gate: PASS)
echo.
echo === [2/2] adapter check: storyboard.pipeline.json ======
echo     (expect 0 errors; any [error] line must be fixed)
python scripts\storyboard_to_cards.py --storyboard video-line\storyboard.pipeline.json --out "%TEMP%\video-line-selfcheck"
if errorlevel 1 (echo [2/2] adapter check: FAIL) else (echo [2/2] adapter check: PASS)
echo.
echo Done. If both lines above say PASS, the line is intact.
pause

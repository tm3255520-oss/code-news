@echo off
REM Run Bilibili candidate collector on host to get PRECISE author medians
REM Host machine has logged-in Bilibili / clean IP, so space API works.
chcp 65001 >nul
cd /d C:\Users\Administrator\Documents\code-news\.agents\skills\viral-video-breakdown
python scripts\collect_bili_candidates.py --config config.yaml --out-dir C:\Users\Administrator\Documents\code-news\research\dsh-std-video-analysis\candidate_pool
echo.
echo Done. Check candidate_pool_*.md for author_median column.
pause

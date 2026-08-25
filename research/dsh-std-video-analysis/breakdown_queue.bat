@echo off
REM One-click entry: paste a Bilibili/Toutiao video URL into the breakdown queue.
REM Claude (or run_breakdown.py) will process queued URLs.
set QUEUE=C:\Users\Administrator\Documents\code-news\research\dsh-std-video-analysis\breakdown_queue
if not exist "%QUEUE%" mkdir "%QUEUE%"
echo ============================================
echo  Paste a video URL, press Enter to queue it.
echo  Example: https://www.bilibili.com/video/BV1xxxx
echo ============================================
set /p LINK=URL:
if "%LINK%"=="" goto end
echo %LINK% >> "%QUEUE%\queue.txt"
echo.
echo  Saved to queue. Claude will auto-process it.
echo  (Queue file: %QUEUE%\queue.txt)
:end
echo.
pause

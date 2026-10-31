@echo off
REM Produce DSH slideshow video: edge-tts voiceover + compose 1280x720.
REM Uses Hermes venv python + existing voice_segmenter.py (no new installs).
chcp 65001 >nul
set PY=C:\Users\Administrator\.hermes\hermes-agent\venv\Scripts\python.exe
set BASE=C:\Users\Administrator\Documents\code-news\research\dsh-std-video-analysis\dsh-video-prod
echo [1/2] Generating voiceover (edge-tts, mature male voice)...
"%PY%" "C:\Users\Administrator\.hermes\scripts\video_enhance\voice_segmenter.py" --script "%BASE%\script.json" --out-dir "%BASE%\voice" --voice yunjian --engine edge
if errorlevel 1 goto fail
echo [2/2] Composing 1280x720 video...
"%PY%" "C:\Users\Administrator\Documents\code-news\scripts\compose_slideshow_video.py" --slides "%BASE%\slides.json" --voice-mp3 "%BASE%\voice\voice_segmented.mp3" --voice-srt "%BASE%\voice\voice_segmented.srt" --out "%BASE%\output.mp4"
if errorlevel 1 goto fail
echo.
echo DONE. Video saved to %BASE%\output.mp4
pause
exit /b 0
:fail
echo FAILED - see messages above.
pause
exit /b 1

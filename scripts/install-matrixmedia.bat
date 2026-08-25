@echo off
setlocal
REM ============================================================
REM  MatrixMedia install helper (ASCII only)
REM  Downloads latest Windows release from GitHub and unpacks
REM  to D:\OpenClaw\MatrixMedia
REM ============================================================
set DEST=D:\OpenClaw\MatrixMedia
if not exist "%DEST%" mkdir "%DEST%"

echo [1/3] Querying latest MatrixMedia release...
powershell -NoProfile -Command "$r = Invoke-RestMethod 'https://api.github.com/repos/hanliang97/MatrixMedia/releases/latest'; $a = $r.assets | Where-Object { $_.name -match 'win|windows|x64' -or $_.name -match '\.zip$' } | Select-Object -First 1; if (-not $a) { Write-Host 'ERR: no matching asset'; exit 1 }; $r.tag_name | Out-File -Encoding ascii '%DEST%\version.txt'; $a.browser_download_url | Out-File -Encoding ascii '%DEST%\asset_url.txt'; Write-Host ('Latest tag: ' + $r.tag_name); Write-Host ('Asset: ' + $a.name)"

echo [2/3] Downloading...
set /p URL=<"%DEST%\asset_url.txt"
powershell -NoProfile -Command "Invoke-WebRequest -Uri '%URL%' -OutFile '%DEST%\matrixmedia.zip'"
if errorlevel 1 (
  echo ERR: download failed. Check network / proxy.
  pause
  exit /b 1
)

echo [3/3] Unpacking to %DEST%...
powershell -NoProfile -Command "Expand-Archive -Path '%DEST%\matrixmedia.zip' -DestinationPath '%DEST%' -Force"
if errorlevel 1 (
  echo ERR: unpack failed. The archive may need 7-Zip.
  pause
  exit /b 1
)

echo.
echo DONE. Next steps:
echo   1. Run MatrixMedia.exe inside %DEST%
echo   2. In the app settings, enable "MCP Server" (open a port)
echo   3. Note the MCP endpoint, then register it in toolkit config
echo      (see docs/MatrixMediaJuMei-Integration-2026-08-26.md)
echo.
pause

@echo off
rem Run the home relay by hand (desktop shortcut "PharmaLens relay now"): upload the blocked sources, then run their feed.
title PharmaLens relay
echo Fetching and uploading...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0relay.ps1"
echo.
echo Running the UP blacklist feed (takes a few minutes)...
curl -s -m 300 -X POST https://srv1.tailf3b6bc.ts.net/api/v1/admin/connectors/upmscl_debarments/run
echo.
echo.
echo Latest relay log:
powershell -NoProfile -Command "Get-Content 'D:\pharmacopy\tmp\relay.log' -Tail 3"
echo.
pause

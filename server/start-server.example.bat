@echo off
rem Starts the tracker server + dashboard. Token must match firmware config.h.
set API_TOKEN=paste-a-long-random-token-here
rem No dashboard password locally: say so explicitly, or the server
rem refuses to start (it can't tell localhost from the internet).
set ALLOW_OPEN_DASHBOARD=1
cd /d "%~dp0"
uvicorn app:app --host 0.0.0.0 --port 8000

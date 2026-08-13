@echo off
rem Starts the tracker server + dashboard. Token must match firmware config.h.
set API_TOKEN=paste-a-long-random-token-here
cd /d "%~dp0"
uvicorn app:app --host 0.0.0.0 --port 8000

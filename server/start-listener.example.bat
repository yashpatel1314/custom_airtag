@echo off
rem Starts the PC's own BLE listener (the zone where the server machine sits).
rem Token must match start-server.bat. Bluetooth must be ON
rem (..\tools\enable-bluetooth.ps1 turns it on from a shell).
cd /d "%~dp0"
python listener.py --server http://127.0.0.1:8000 --token paste-a-long-random-token-here --listener home

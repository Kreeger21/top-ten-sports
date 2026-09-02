@echo off
set "TOP_TEN_ENV=test"
set "TOP_TEN_HOST=127.0.0.1"
set "TOP_TEN_PORT=5000"
cd /d "%~dp0"
".venv\Scripts\python.exe" app.py


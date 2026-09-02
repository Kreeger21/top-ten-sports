@echo off
set "TOP_TEN_ENV=production"
cd /d "%~dp0"
".venv\Scripts\python.exe" -m waitress --listen=127.0.0.1:8000 app:app


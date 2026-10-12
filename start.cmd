@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Please create the Python environment first. See README.md.
  pause
  exit /b 1
)
echo Open http://127.0.0.1:8765
".venv\Scripts\python.exe" -m uvicorn vault.app:app --host 127.0.0.1 --port 8765

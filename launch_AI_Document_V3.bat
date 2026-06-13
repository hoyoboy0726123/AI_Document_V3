@echo off
cd /d "%~dp0"
echo [Launcher] Starting AI_Document_V3...

start cmd /k "cd backend && .venv\Scripts\python.exe -u -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
start cmd /k "cd frontend && set VITE_API_TARGET=http://127.0.0.1:8001 && npm run dev -- --host --port 5175"

echo [Launcher] Applications started!
echo Backend: http://127.0.0.1:8001
echo Frontend: http://localhost:5175
pause

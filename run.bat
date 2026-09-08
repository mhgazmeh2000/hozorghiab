@echo off
setlocal
cd /d "%~dp0"

echo Starting backend...
start "Backend" /D "%~dp0backend" cmd /k "python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

echo Starting frontend...
start "Frontend" /D "%~dp0frontend" cmd /k "npm run dev -- --host 127.0.0.1"

echo.
echo Project is launching...
echo Backend: http://127.0.0.1:8000
echo Frontend: http://127.0.0.1:5173
echo API docs: http://127.0.0.1:8000/api/docs
echo.
echo This launcher window will close after a moment.
choice /C Q /N /T 3 /D Q >nul

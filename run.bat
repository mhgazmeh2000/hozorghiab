@echo off
REM =====================================================================
REM  Attendance Manager - Windows one-click launcher
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

title Attendance Manager Launcher

echo ============================================================
echo   Attendance Manager - Windows Launcher
echo ============================================================
echo    Working directory: %cd%
echo ============================================================
echo.

REM ---------- 0. Prerequisites ----------
echo [0/6] Checking prerequisites ...
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python was not found in PATH. Install Python 3.11+ and
    echo         enable "Add Python to PATH" during setup.
    pause & exit /b 1
)
for /f "tokens=*" %%V in ('python -c "import sys;print('%%d.%%d'%%sys.version_info[:2])"') do set PYVER=%%V
echo       - Python version: %PYVER%

where npm >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js / npm was not found in PATH. Install Node.js 18+
    echo         from https://nodejs.org and try again.
    pause & exit /b 1
)
for /f "tokens=*" %%V in ('node -v') do set NODEVER=%%V
echo       - Node version: %NODEVER%

REM ---------- 1. Stop existing services on 8000/5173 ----------
echo [1/6] Freeing ports 8000 and 5173 ...
call stop.bat >nul
timeout /t 1 /nobreak >nul

for %%P in (8000 5173) do (
    netstat -ano 2>nul | findstr /R /C:":%%P " | findstr LISTENING >nul
    if not errorlevel 1 (
        echo [ERROR] Port %%P is still occupied.
        echo         Identify PID with:   netstat -ano ^| findstr :%%P
        echo         Then kill with:       taskkill /F /PID ^<pid^>
        echo         Then re-run run.bat.
        pause & exit /b 1
    )
)
echo       - Ports 8000 and 5173 are free.

REM ---------- 2. Backend venv ----------
echo [2/6] Preparing backend virtual environment ...
if not exist "backend\venv\Scripts\python.exe" (
    echo       - Creating backend\venv ...
    python -m venv backend\venv
)
echo       - Activating backend\venv and installing Python dependencies ...
call "backend\venv\Scripts\activate.bat"
python -m pip install --upgrade pip --quiet
pip install -r backend\requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] pip install failed. Check network and re-run.
    pause & exit /b 1
)

REM ---------- 3. Backend .env ----------
echo [3/6] Backend environment file ...
if not exist "backend\.env" (
    echo       - backend\.env not found; creating from .env.example ...
    copy /Y ".env.example" "backend\.env" >nul

    echo       - Generating stable SECRET_KEY and Fernet key ...
    for /f "delims=" %%K in ('python -c "import secrets;print(secrets.token_hex(32))"') do set "SECRET_KEY=%%K"
    for /f "delims=" %%F in ('python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"') do set "FERNET_KEY=%%F"

    set "ENV_FILE=backend\.env"
    set "BSK=admin123"
    set "BOP=operator123"
    set "BVI=viewer123"
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "$p=$env:ENV_FILE; $c=Get-Content $p -Raw;" ^
      "$c=$c -replace '(?m)^SECRET_KEY=.*$',('SECRET_KEY='+$env:SECRET_KEY);" ^
      "$c=$c -replace '(?m)^CREDENTIAL_ENCRYPTION_KEY=.*$',('CREDENTIAL_ENCRYPTION_KEY='+$env:FERNET_KEY);" ^
      "$c=$c -replace '(?m)^BOOTSTRAP_ADMIN_PASSWORD=.*$',('BOOTSTRAP_ADMIN_PASSWORD='+$env:BSK);" ^
      "$c=$c -replace '(?m)^BOOTSTRAP_OPERATOR_PASSWORD=.*$',('BOOTSTRAP_OPERATOR_PASSWORD='+$env:BOP);" ^
      "$c=$c -replace '(?m)^BOOTSTRAP_VIEWER_PASSWORD=.*$',('BOOTSTRAP_VIEWER_PASSWORD='+$env:BVI);" ^
      "$c=$c -replace '(?m)^ENABLE_SCHEDULER=.*$','ENABLE_SCHEDULER=false';" ^
      "Set-Content -Path $p -Value $c -Encoding UTF8"

    if exist "backend\attendance.db" (
        echo       - Removing leftover attendance.db so new bootstrap passwords apply ...
        del /F /Q backend\attendance.db backend\attendance.db-shm backend\attendance.db-wal >nul 2>nul
    )

    echo       ====================================================
    echo         First-run logins:
    echo             admin    / admin123
    echo             operator / operator123
    echo             viewer   / viewer123
    echo       ====================================================
) else (
    echo       - backend\.env exists, leaving it as-is.
)

REM ---------- 4. Frontend deps ----------
echo [4/6] Preparing frontend ...
if not exist "frontend\node_modules\vite\bin\vite.js" (
    echo       - Running npm install in frontend ...
    pushd frontend
    call npm install
    popd
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        pause & exit /b 1
    )
) else (
    echo       - node_modules present, skipping npm install.
)

REM ---------- 5. Launch ----------
echo [5/6] Launching backend and frontend ...
start "Attendance Backend (API)" /D "%cd%\backend" cmd /k "title Attendance Backend (API) && venv\Scripts\activate.bat && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
start "Attendance Frontend (Vite)" /D "%cd%\frontend" cmd /k "title Attendance Frontend (Vite) && npm run dev -- --host 127.0.0.1"

REM ---------- 6. Wait and open browser ----------
echo [6/6] Waiting for servers ...
set /a TRIES=0
:waitapi
set /a TRIES+=1
if %TRIES% GTR 25 goto opendone
timeout /t 1 /nobreak >nul
powershell -NoProfile -Command "try { (Invoke-WebRequest -UseBasicParsing -Uri http://127.0.0.1:8000/api/openapi.json -TimeoutSec 2).StatusCode } catch { exit 1 }" >nul 2>nul
if errorlevel 1 goto waitapi
:opendone

echo.
echo ============================================================
echo   Services started:
echo     Backend : http://127.0.0.1:8000
echo     API docs: http://127.0.0.1:8000/api/docs
echo     Frontend: http://127.0.0.1:5173
echo ============================================================
start "" "http://127.0.0.1:5173/"

endlocal
exit /b 0
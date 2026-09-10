@echo off
REM =====================================================================
REM  Attendance Manager - Stop all services (Windows)
REM =====================================================================
setlocal
cd /d "%~dp0"

echo [Attendance] Stopping services on ports 8000 and 5173 ...

powershell -NoProfile -ExecutionPolicy Bypass -Command "foreach ($p in @(8000,5173)) { Get-NetTCPConnection -LocalPort $p -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Write-Host ('    Killing PID ' + $_.OwningProcess + ' on port ' + $p); Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue } }" >nul 2>nul

for %%P in (8000 5173) do for /f "tokens=5" %%A in ('netstat -ano 2^>nul ^| findstr /R /C:":%%P " ^| findstr LISTENING') do call :kill_pid %%A %%P

echo.
for %%P in (8000 5173) do call :check_port %%P

endlocal
exit /b 0

:kill_pid
echo     Killing PID %1 on port %2 (netstat fallback) ...
taskkill /F /T /PID %1 >nul 2>nul
exit /b 0

:check_port
netstat -ano 2>nul | findstr /R /C:":%1 " | findstr LISTENING >nul
if not errorlevel 1 echo [WARN] Port %1 is still in use. Please close the program holding it manually.
exit /b 0
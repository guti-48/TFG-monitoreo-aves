@echo off
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%\..\.."

if not defined BIRDMONITOR_BACKEND_HOST set "BIRDMONITOR_BACKEND_HOST=0.0.0.0"
if not defined BIRDMONITOR_BACKEND_PORT set "BIRDMONITOR_BACKEND_PORT=8000"

netstat -ano | findstr /R /C:":%BIRDMONITOR_BACKEND_PORT% .*LISTENING" >nul
if %ERRORLEVEL%==0 (
    echo Backend ya esta escuchando en el puerto %BIRDMONITOR_BACKEND_PORT%.
    exit /b 0
)

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python -m uvicorn backend.app.main:app --host %BIRDMONITOR_BACKEND_HOST% --port %BIRDMONITOR_BACKEND_PORT%
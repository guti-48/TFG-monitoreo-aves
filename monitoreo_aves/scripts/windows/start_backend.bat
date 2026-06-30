@echo off
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%\..\.."

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if %ERRORLEVEL%==0 (
    echo Backend ya esta escuchando en el puerto 8000.
    exit /b 0
)

if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat
)

python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
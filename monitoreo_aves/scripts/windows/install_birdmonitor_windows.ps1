# BirdMonitor Windows Installer
# Ejecutar como administrador

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " BirdMonitor Windows Installer" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

# =========================
# COMPROBAR ADMIN
# =========================

$currentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($currentUser)
$isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    throw "Este script debe ejecutarse como administrador."
}

# =========================
# DETECTAR RAIZ DEL REPO
# =========================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Resolve-Path (Join-Path $ScriptDir "..\..")

Write-Host "Proyecto detectado en:" -ForegroundColor Yellow
Write-Host $ProjectDir
Write-Host ""

if (!(Test-Path (Join-Path $ProjectDir "backend"))) {
    throw "No se ha encontrado la carpeta backend/. Ejecuta este script desde scripts/windows dentro del repo."
}

if (!(Test-Path (Join-Path $ProjectDir "backend\app\main.py"))) {
    throw "No se ha encontrado backend/app/main.py. Revisa la estructura del proyecto."
}

# =========================
# DETECTAR MEDIAMTX
# =========================

Write-Host "Buscando MediaMTX..." -ForegroundColor Cyan

$PossibleMediaMtxExe = @(
    (Join-Path $ProjectDir "mediamtx.exe"),
    (Join-Path $ProjectDir "tools\mediamtx\mediamtx.exe"),
    (Join-Path $ProjectDir "external\mediamtx\mediamtx.exe"),
    "C:\mediamtx.exe"
)

$MediaMtxExe = $null

foreach ($path in $PossibleMediaMtxExe) {
    if (Test-Path $path) {
        $MediaMtxExe = Resolve-Path $path
        break
    }
}

if ($null -eq $MediaMtxExe) {
    Write-Host "No se ha encontrado mediamtx.exe automaticamente." -ForegroundColor Yellow
    $manualPath = Read-Host "Introduce la ruta completa de mediamtx.exe"

    if (!(Test-Path $manualPath)) {
        throw "No existe mediamtx.exe en la ruta indicada: $manualPath"
    }

    $MediaMtxExe = Resolve-Path $manualPath
}

$MediaMtxDir = Split-Path -Parent $MediaMtxExe

# =========================
# DETECTAR CONFIG MEDIAMTX
# =========================

$PossibleMediaMtxConfig = @(
    (Join-Path $MediaMtxDir "mediamtx.yml"),
    (Join-Path $ProjectDir "mediamtx.yml"),
    (Join-Path $ProjectDir "tools\mediamtx\mediamtx.yml"),
    "C:\mediamtx.yml"
)

$MediaMtxConfig = $null

foreach ($path in $PossibleMediaMtxConfig) {
    if (Test-Path $path) {
        $MediaMtxConfig = Resolve-Path $path
        break
    }
}

if ($null -eq $MediaMtxConfig) {
    Write-Host "No se ha encontrado mediamtx.yml automaticamente." -ForegroundColor Yellow
    $manualConfig = Read-Host "Introduce la ruta completa de mediamtx.yml"

    if (!(Test-Path $manualConfig)) {
        throw "No existe mediamtx.yml en la ruta indicada: $manualConfig"
    }

    $MediaMtxConfig = Resolve-Path $manualConfig
}

Write-Host "MediaMTX detectado:" -ForegroundColor Green
Write-Host "EXE: $MediaMtxExe"
Write-Host "YML: $MediaMtxConfig"
Write-Host ""

# =========================
# PREPARAR CARPETA LOCAL DE SCRIPTS
# =========================

$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$MediaMtxStartScript = Join-Path $RuntimeDir "start_mediamtx.ps1"
$BackendStartScript = Join-Path $RuntimeDir "start_backend.bat"
$MediaMtxOutLog = Join-Path $RuntimeDir "mediamtx.out.log"
$MediaMtxErrLog = Join-Path $RuntimeDir "mediamtx.err.log"
$BackendLog = Join-Path $RuntimeDir "backend.log"

$MediaMtxTaskName = "BirdMonitor MediaMTX"
$BackendTaskName = "BirdMonitor Backend"

# =========================
# CREAR SCRIPT MEDIAMTX
# =========================

Write-Host "Creando script de arranque de MediaMTX..." -ForegroundColor Cyan

@"
`$ErrorActionPreference = "Stop"

`$existing = Get-Process mediamtx -ErrorAction SilentlyContinue

if (`$existing) {
    exit 0
}

Start-Process `
    -FilePath "$MediaMtxExe" `
    -ArgumentList "$MediaMtxConfig" `
    -WorkingDirectory "$MediaMtxDir" `
    -WindowStyle Hidden `
    -RedirectStandardOutput "$MediaMtxOutLog" `
    -RedirectStandardError "$MediaMtxErrLog"
"@ | Set-Content -Path $MediaMtxStartScript -Encoding UTF8

# =========================
# CREAR SCRIPT BACKEND
# =========================

Write-Host "Creando script de arranque del backend FastAPI..." -ForegroundColor Cyan

$VenvActivate = Join-Path $ProjectDir "venv\Scripts\activate.bat"

if (Test-Path $VenvActivate) {
    $ActivateLine = "call `"$VenvActivate`""
} else {
    $ActivateLine = "REM No se ha encontrado venv. Se usara python del sistema."
}

@"
@echo off
cd /d "$ProjectDir"

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if %ERRORLEVEL%==0 (
    echo Backend ya esta escuchando en el puerto 8000. >> "$BackendLog"
    exit /b 0
)

$ActivateLine

python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 >> "$BackendLog" 2>&1
"@ | Set-Content -Path $BackendStartScript -Encoding ASCII

# =========================
# ELIMINAR TAREAS ANTIGUAS
# =========================

Write-Host "Eliminando tareas anteriores si existen..." -ForegroundColor Cyan

Unregister-ScheduledTask -TaskName $MediaMtxTaskName -Confirm:$false -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $BackendTaskName -Confirm:$false -ErrorAction SilentlyContinue

# =========================
# CREAR TAREAS PROGRAMADAS
# =========================

$Trigger = New-ScheduledTaskTrigger -AtLogOn

Write-Host "Creando tarea programada para MediaMTX..." -ForegroundColor Cyan

$MediaMtxAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$MediaMtxStartScript`"" `
    -WorkingDirectory "$RuntimeDir"

Register-ScheduledTask `
    -TaskName $MediaMtxTaskName `
    -Action $MediaMtxAction `
    -Trigger $Trigger `
    -Description "Arranca MediaMTX para BirdMonitor" `
    -RunLevel Highest `
    -Force

Write-Host "Creando tarea programada para Backend FastAPI..." -ForegroundColor Cyan

$BackendAction = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$BackendStartScript`"" `
    -WorkingDirectory "$ProjectDir"

Register-ScheduledTask `
    -TaskName $BackendTaskName `
    -Action $BackendAction `
    -Trigger $Trigger `
    -Description "Arranca el backend FastAPI de BirdMonitor" `
    -RunLevel Highest `
    -Force

# =========================
# ARRANCAR
# =========================

Write-Host "Arrancando tareas..." -ForegroundColor Cyan

Start-ScheduledTask -TaskName $MediaMtxTaskName
Start-ScheduledTask -TaskName $BackendTaskName

Start-Sleep -Seconds 4

Write-Host ""
Write-Host "Comprobando puertos..." -ForegroundColor Cyan

Write-Host ""
Write-Host "Puerto 8888 MediaMTX:" -ForegroundColor Yellow
netstat -ano | findstr ":8888"

Write-Host ""
Write-Host "Puerto 8000 Backend:" -ForegroundColor Yellow
netstat -ano | findstr ":8000"

Write-Host ""
Write-Host "Tarea MediaMTX:" -ForegroundColor Yellow
Get-ScheduledTaskInfo -TaskName $MediaMtxTaskName | Format-List LastRunTime,LastTaskResult

Write-Host ""
Write-Host "Tarea Backend:" -ForegroundColor Yellow
Get-ScheduledTaskInfo -TaskName $BackendTaskName | Format-List LastRunTime,LastTaskResult

Write-Host ""
Write-Host "Instalacion completada." -ForegroundColor Green
Write-Host "Backend:  http://127.0.0.1:8000"
Write-Host "MediaMTX: http://127.0.0.1:8888"
Write-Host ""
Write-Host "Logs en:"
Write-Host $RuntimeDir

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
    (Join-Path $ProjectDir "tools\mediamtx\mediamtx.yml"),
    (Join-Path $ProjectDir "mediamtx.yml"),
    (Join-Path $MediaMtxDir "mediamtx.yml"),
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
    Wait-Process -Id `$existing.Id
    exit 1
}

`$startArgs = @{
    FilePath = "$MediaMtxExe"
    ArgumentList = @("$MediaMtxConfig")
    WorkingDirectory = "$MediaMtxDir"
    WindowStyle = "Hidden"
    RedirectStandardOutput = "$MediaMtxOutLog"
    RedirectStandardError = "$MediaMtxErrLog"
}

`$process = Start-Process @startArgs -PassThru -Wait
exit `$process.ExitCode
"@ | Set-Content -Path $MediaMtxStartScript -Encoding UTF8

# =========================
# CREAR SCRIPT BACKEND
# =========================

Write-Host "Creando script de arranque del backend FastAPI..." -ForegroundColor Cyan

$VenvPython = Join-Path $ProjectDir "venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $PythonExe = (Resolve-Path $VenvPython).Path
} else {
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue

    if ($null -eq $PythonCommand) {
        throw "No se ha encontrado venv\Scripts\python.exe ni python.exe en PATH."
    }

    $PythonExe = $PythonCommand.Source
}

@"
@echo off
cd /d "$ProjectDir"

if not defined BIRDMONITOR_BACKEND_HOST set "BIRDMONITOR_BACKEND_HOST=0.0.0.0"
if not defined BIRDMONITOR_BACKEND_PORT set "BIRDMONITOR_BACKEND_PORT=8000"

netstat -ano | findstr /R /C:":%BIRDMONITOR_BACKEND_PORT% .*LISTENING" >nul
if %ERRORLEVEL%==0 (
    echo Backend ya esta escuchando en el puerto %BIRDMONITOR_BACKEND_PORT%. >> "$BackendLog"
    exit /b 0
)

"$PythonExe" -m uvicorn backend.app.main:app --host %BIRDMONITOR_BACKEND_HOST% --port %BIRDMONITOR_BACKEND_PORT% >> "$BackendLog" 2>&1
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

$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal `
    -UserId $TaskUser `
    -LogonType S4U `
    -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

Write-Host "Las tareas arrancaran con Windows como $TaskUser." -ForegroundColor Yellow
Write-Host ""

Write-Host "Creando tarea programada para MediaMTX..." -ForegroundColor Cyan

$MediaMtxAction = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-ExecutionPolicy Bypass -File `"$MediaMtxStartScript`"" `
    -WorkingDirectory "$RuntimeDir"

Register-ScheduledTask `
    -TaskName $MediaMtxTaskName `
    -Action $MediaMtxAction `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Arranca MediaMTX para BirdMonitor" `
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
    -Principal $Principal `
    -Settings $Settings `
    -Description "Arranca el backend FastAPI de BirdMonitor" `
    -Force

if ($null -eq (Get-ScheduledTask -TaskName $MediaMtxTaskName -ErrorAction SilentlyContinue)) {
    throw "No se pudo registrar la tarea $MediaMtxTaskName."
}

if ($null -eq (Get-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue)) {
    throw "No se pudo registrar la tarea $BackendTaskName."
}

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

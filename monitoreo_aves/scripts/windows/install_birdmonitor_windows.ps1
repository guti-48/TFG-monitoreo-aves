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
$ApplyNetworkMode = Join-Path $ScriptDir "apply_network_mode.ps1"
$HiddenLauncher = Join-Path $ScriptDir "run_powershell_hidden.vbs"

Write-Host "Proyecto detectado en:" -ForegroundColor Yellow
Write-Host $ProjectDir
Write-Host ""

if (!(Test-Path (Join-Path $ProjectDir "backend"))) {
    throw "No se ha encontrado la carpeta backend/. Ejecuta este script desde scripts/windows dentro del repo."
}

if (!(Test-Path (Join-Path $ProjectDir "backend\app\main.py"))) {
    throw "No se ha encontrado backend/app/main.py. Revisa la estructura del proyecto."
}
if (-not (Test-Path -LiteralPath $HiddenLauncher)) {
    throw "No se ha encontrado scripts\windows\run_powershell_hidden.vbs."
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

$SecureMediaMtxConfig = Join-Path `
    $ProjectDir `
    "tools\mediamtx\mediamtx.secure.yml"
if (-not (Test-Path -LiteralPath $SecureMediaMtxConfig)) {
    throw (
        "Falta tools/mediamtx/mediamtx.secure.yml. " +
        "BirdMonitor no arrancara con la configuracion publica antigua."
    )
}
$MediaMtxConfig = Resolve-Path -LiteralPath $SecureMediaMtxConfig

Write-Host "MediaMTX detectado:" -ForegroundColor Green
Write-Host "EXE: $MediaMtxExe"
Write-Host "YML: $MediaMtxConfig"
Write-Host ""

$BackendEnv = Join-Path $ProjectDir "backend\birdmonitor.env"
if (-not (Test-Path -LiteralPath $BackendEnv)) {
    throw (
        "Falta backend/birdmonitor.env. Ejecuta primero " +
        "scripts/configure_security.py y " +
        "scripts/configure_stream_security.py."
    )
}

$BackendEnvContent = Get-Content -LiteralPath $BackendEnv -Raw
foreach ($RequiredKey in @(
    "BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH",
    "BIRDMONITOR_STREAM_READER_PASSWORD",
    "BIRDMONITOR_STREAM_PROXY_PASSWORD",
    "BIRDMONITOR_NETWORK_MODE",
    "BIRDMONITOR_SERVER_HOST"
)) {
    if ($BackendEnvContent -notmatch "(?m)^$RequiredKey=.+$") {
        throw (
            "Falta $RequiredKey. Ejecuta primero " +
            "python scripts/configure_stream_security.py."
        )
    }
}
$EnvValues = @{}
foreach ($RawLine in Get-Content -LiteralPath $BackendEnv) {
    if ($RawLine -match "^\s*([^#][^=]*)=(.*)$") {
        $EnvValues[$Matches[1].Trim()] = $Matches[2].Trim()
    }
}
$NetworkMode = $EnvValues["BIRDMONITOR_NETWORK_MODE"]
$ServerHost = $EnvValues["BIRDMONITOR_SERVER_HOST"]
if ($NetworkMode -notin @("local", "tailscale")) {
    throw (
        "Ejecuta primero python scripts/configure_network_mode.py " +
        "--mode local|tailscale."
    )
}
if ($null -eq (Get-NetIPAddress `
    -IPAddress $ServerHost `
    -ErrorAction SilentlyContinue
)) {
    throw "La IP configurada $ServerHost no pertenece a este servidor."
}

# =========================
# PREPARAR CARPETA LOCAL DE SCRIPTS
# =========================

$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
$RuntimeMediaMtxConfig = Join-Path `
    $RuntimeDir `
    "mediamtx.secure.runtime.yml"
$SecureConfigContent = Get-Content `
    -LiteralPath $SecureMediaMtxConfig `
    -Raw
$RtspAddressPattern = "(?m)^rtspAddress:\s*:8554\s*$"
if (
    [regex]::Matches(
        $SecureConfigContent,
        $RtspAddressPattern
    ).Count -ne 1
) {
    throw "No se encontro una unica directiva rtspAddress en MediaMTX."
}
$RuntimeConfigContent = [regex]::Replace(
    $SecureConfigContent,
    $RtspAddressPattern,
    "rtspAddress: ${ServerHost}:8554"
)
[IO.File]::WriteAllText(
    $RuntimeMediaMtxConfig,
    $RuntimeConfigContent,
    (New-Object Text.UTF8Encoding($false))
)
$MediaMtxConfig = $RuntimeMediaMtxConfig

$MediaMtxStartScript = Join-Path $RuntimeDir "start_mediamtx.ps1"
$BackendStartScript = Join-Path $ScriptDir "run_backend_hidden.ps1"
$MediaMtxOutLog = Join-Path $RuntimeDir "mediamtx.out.log"
$MediaMtxErrLog = Join-Path $RuntimeDir "mediamtx.err.log"

$MediaMtxTaskName = "BirdMonitor MediaMTX"
$BackendTaskName = "BirdMonitor Backend"

# =========================
# CREAR SCRIPT MEDIAMTX
# =========================

Write-Host "Creando script de arranque de MediaMTX..." -ForegroundColor Cyan

@"
`$ErrorActionPreference = "Stop"
function Test-BirdMonitorLocalAddress {
    param([string]`$Address)

    `$Addresses = [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        ForEach-Object { `$_.GetIPProperties().UnicastAddresses } |
        ForEach-Object { `$_.Address.IPAddressToString }
    return `$Addresses -contains `$Address
}

`$AddressDeadline = (Get-Date).AddMinutes(3)
while (-not (Test-BirdMonitorLocalAddress "$ServerHost")) {
    if ((Get-Date) -ge `$AddressDeadline) {
        Write-Error (
            "La IP segura $ServerHost no esta disponible " +
            "despues de esperar a la red."
        )
        exit 2
    }
    Start-Sleep -Seconds 2
}

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

if (-not (Test-Path -LiteralPath $VenvPython)) {
    throw "No se ha encontrado venv\Scripts\python.exe."
}
if (-not (Test-Path -LiteralPath $BackendStartScript)) {
    throw "No se ha encontrado scripts\windows\run_backend_hidden.ps1."
}

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
$Trigger = New-ScheduledTaskTrigger -AtLogOn -User $TaskUser
$Principal = New-ScheduledTaskPrincipal `
    -UserId $TaskUser `
    -LogonType Interactive `
    -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Seconds 0) `
    -MultipleInstances IgnoreNew

Write-Host "Las tareas arrancaran al iniciar sesion como $TaskUser." -ForegroundColor Yellow
Write-Host ""

Write-Host "Creando tarea programada para MediaMTX..." -ForegroundColor Cyan

$MediaMtxAction = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$HiddenLauncher`" `"$MediaMtxStartScript`"" `
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
    -Execute "wscript.exe" `
    -Argument "`"$HiddenLauncher`" `"$BackendStartScript`"" `
    -WorkingDirectory "$ProjectDir"

Register-ScheduledTask `
    -TaskName $BackendTaskName `
    -Action $BackendAction `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Arranca en segundo plano el backend FastAPI de BirdMonitor" `
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

Write-Host "Aplicando perfil de red y Firewall..." -ForegroundColor Cyan
& $ApplyNetworkMode

Write-Host ""
Write-Host "Instalacion completada." -ForegroundColor Green
Write-Host "Dashboard: http://${ServerHost}:8000"
Write-Host "MediaMTX HLS interno: http://127.0.0.1:8888"
Write-Host "Dashboard HLS protegido: /stream/hls/..."
Write-Host ""
Write-Host "Logs en:"
Write-Host $RuntimeDir

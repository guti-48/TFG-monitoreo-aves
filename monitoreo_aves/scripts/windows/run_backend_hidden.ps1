# Lanzador supervisado del backend. La tarea programada lo ejecuta mediante
# run_powershell_hidden.vbs para no crear una consola que el usuario pueda
# cerrar accidentalmente.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$PythonExe = Join-Path $ProjectDir "venv\Scripts\python.exe"
$BackendEnv = Join-Path $ProjectDir "backend\birdmonitor.env"
$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
$BackendLog = Join-Path $RuntimeDir "backend.log"
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)

function Write-BackendLog {
    param([object]$Value)

    [IO.File]::AppendAllText(
        $BackendLog,
        ([string]$Value) + [Environment]::NewLine,
        $Utf8NoBom
    )
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "No se encuentra el Python del entorno virtual: $PythonExe"
}
if (-not (Test-Path -LiteralPath $BackendEnv)) {
    throw "No se encuentra la configuracion privada: $BackendEnv"
}

$EnvValues = @{}
foreach ($RawLine in Get-Content -LiteralPath $BackendEnv) {
    $Line = $RawLine.Trim()
    if (-not $Line -or $Line.StartsWith("#") -or $Line -notmatch "=") {
        continue
    }
    $Key, $Value = $Line.Split("=", 2)
    $EnvValues[$Key.Trim()] = $Value.Trim().Trim('"').Trim("'")
}

$BackendHost = if ($env:BIRDMONITOR_BACKEND_HOST) {
    $env:BIRDMONITOR_BACKEND_HOST
} elseif ($EnvValues["BIRDMONITOR_BACKEND_HOST"]) {
    $EnvValues["BIRDMONITOR_BACKEND_HOST"]
} else {
    "0.0.0.0"
}
$BackendPort = if ($env:BIRDMONITOR_BACKEND_PORT) {
    [int]$env:BIRDMONITOR_BACKEND_PORT
} elseif ($EnvValues["BIRDMONITOR_BACKEND_PORT"]) {
    [int]$EnvValues["BIRDMONITOR_BACKEND_PORT"]
} else {
    8000
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
Write-BackendLog ""
Write-BackendLog (
    "=== Inicio backend oculto: " +
    (Get-Date -Format "yyyy-MM-dd HH:mm:ss") +
    " ==="
)

$ExistingListener = Get-NetTCPConnection `
    -LocalPort $BackendPort `
    -State Listen `
    -ErrorAction SilentlyContinue
if ($ExistingListener) {
    Write-BackendLog (
        "No se inicia otra instancia: el puerto $BackendPort ya escucha."
    )
    exit 0
}

$BackendExitCode = 1
Push-Location $ProjectDir
try {
    # Uvicorn escribe sus mensajes INFO en stderr. Windows PowerShell 5 los
    # representa como ErrorRecord al combinar 2>&1; no deben convertirse en
    # excepciones por el ErrorActionPreference global del lanzador.
    $PreviousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $PythonExe `
        -m uvicorn backend.app.main:app `
        --host $BackendHost `
        --port $BackendPort 2>&1 |
        ForEach-Object {
            Write-BackendLog $_
        }
    $BackendExitCode = $LASTEXITCODE
}
catch {
    Write-BackendLog ("Error del lanzador: " + $_.Exception.Message)
}
finally {
    $ErrorActionPreference = $PreviousErrorActionPreference
    Pop-Location
}

Write-BackendLog (
    "=== Fin backend: " +
    (Get-Date -Format "yyyy-MM-dd HH:mm:ss") +
    " codigo $BackendExitCode ==="
)
exit $BackendExitCode

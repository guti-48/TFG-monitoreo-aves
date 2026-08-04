# Repara exclusivamente la tarea programada del backend BirdMonitor.
# Ejecutar desde PowerShell como administrador.

$ErrorActionPreference = "Stop"

$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$PrincipalCheck = New-Object Security.Principal.WindowsPrincipal($CurrentUser)
$IsAdmin = $PrincipalCheck.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $IsAdmin) {
    throw "Abre PowerShell como administrador y vuelve a ejecutar el script."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$PythonExe = Join-Path $ProjectDir "venv\Scripts\python.exe"
$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
$RunnerPath = Join-Path $ScriptDir "run_backend_hidden.ps1"
$HiddenLauncher = Join-Path $ScriptDir "run_powershell_hidden.vbs"
$BackendLog = Join-Path $RuntimeDir "backend.log"
$TaskName = "BirdMonitor Backend"
$BackendPort = if ($env:BIRDMONITOR_BACKEND_PORT) {
    [int]$env:BIRDMONITOR_BACKEND_PORT
} else {
    8000
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "No se encuentra el Python del entorno virtual: $PythonExe"
}
if (-not (Test-Path -LiteralPath $RunnerPath)) {
    throw "No se encuentra el lanzador oculto: $RunnerPath"
}
if (-not (Test-Path -LiteralPath $HiddenLauncher)) {
    throw "No se encuentra el envoltorio sin consola: $HiddenLauncher"
}

if (-not (Test-Path -LiteralPath (Join-Path $ProjectDir "backend\app\main.py"))) {
    throw "No se encuentra backend/app/main.py en $ProjectDir"
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

Write-Host "Eliminando la instancia atascada..." -ForegroundColor Cyan
$ExistingTask = Get-ScheduledTask `
    -TaskName $TaskName `
    -ErrorAction SilentlyContinue

if ($null -ne $ExistingTask) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Unregister-ScheduledTask `
        -TaskName $TaskName `
        -Confirm:$false `
        -ErrorAction Stop
} else {
    Write-Host "La tarea anterior ya estaba eliminada." -ForegroundColor DarkGray
}

# Garantiza que la comprobacion final pertenece a la nueva tarea. Solo detiene
# un proceso que corresponda inequivocamente a este backend.
$ListenerProcessIds = Get-NetTCPConnection `
    -LocalPort $BackendPort `
    -State Listen `
    -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique

foreach ($ListenerProcessId in @($ListenerProcessIds)) {
    $ProcessInfo = Get-CimInstance `
        Win32_Process `
        -Filter "ProcessId = $ListenerProcessId" `
        -ErrorAction SilentlyContinue
    $IsBirdMonitorBackend = (
        $null -ne $ProcessInfo -and
        $ProcessInfo.CommandLine -like "*backend.app.main:app*"
    )

    if (-not $IsBirdMonitorBackend) {
        throw (
            "El puerto $BackendPort esta ocupado por otro proceso " +
            "(PID $ListenerProcessId). No se ha detenido."
        )
    }

    Write-Host (
        "Deteniendo backend anterior (PID $ListenerProcessId)..."
    ) -ForegroundColor DarkGray
    Stop-Process -Id $ListenerProcessId -Force -ErrorAction Stop
}

if (@($ListenerProcessIds).Count -gt 0) {
    Start-Sleep -Seconds 1
}

# Una version anterior del lanzador PowerShell podia mezclar UTF-8 y UTF-16.
# Conserva ese registro para diagnostico y comienza uno limpio.
if (Test-Path -LiteralPath $BackendLog) {
    $LogContainsNull = (
        [System.IO.File]::ReadAllBytes($BackendLog) -contains 0
    )

    if ($LogContainsNull) {
        $Timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $ArchivedLog = Join-Path `
            $RuntimeDir `
            "backend-pre-repair-$Timestamp.log"
        Move-Item `
            -LiteralPath $BackendLog `
            -Destination $ArchivedLog `
            -Force
        Write-Host "Log anterior conservado en: $ArchivedLog" -ForegroundColor DarkGray
    }
}

$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$HiddenLauncher`" `"$RunnerPath`"" `
    -WorkingDirectory $ProjectDir
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

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $Action `
    -Trigger $Trigger `
    -Principal $Principal `
    -Settings $Settings `
    -Description "Arranca en segundo plano el backend seguro de BirdMonitor" `
    -Force | Out-Null

function Test-BirdMonitorHealth {
    try {
        $Health = Invoke-RestMethod `
            -Uri "http://127.0.0.1:$BackendPort/health" `
            -TimeoutSec 3
        return (
            $Health.status -eq "ok" -and
            $Health.network_configured -eq $true -and
            $Health.security_configured -eq $true -and
            (
                $Health.stream_security -ne "required" -or
                $Health.stream_security_configured -eq $true
            )
        )
    }
    catch {
        return $false
    }
}

function Wait-BirdMonitorHealth([int]$TimeoutSeconds) {
    $Deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $Deadline) {
        if (Test-BirdMonitorHealth) {
            return $true
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Test-BirdMonitorStability([int]$Seconds) {
    for ($Index = 0; $Index -lt $Seconds; $Index++) {
        Start-Sleep -Seconds 1
        $CurrentTask = Get-ScheduledTask `
            -TaskName $TaskName `
            -ErrorAction SilentlyContinue
        $Listener = Get-NetTCPConnection `
            -LocalPort $BackendPort `
            -State Listen `
            -ErrorAction SilentlyContinue
        if (
            $null -eq $CurrentTask -or
            $CurrentTask.State -ne "Running" -or
            -not [bool]$Listener -or
            -not (Test-BirdMonitorHealth)
        ) {
            return $false
        }
    }
    return $true
}

Write-Host "Tarea reconstruida. Arrancando backend..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName

$HealthOk = Wait-BirdMonitorHealth 60
$Stable = $HealthOk -and (Test-BirdMonitorStability 10)

if (-not $Stable) {
    Write-Host (
        "El primer proceso no permanecio estable; reintentando una vez..."
    ) -ForegroundColor Yellow
    Start-ScheduledTask -TaskName $TaskName
    $HealthOk = Wait-BirdMonitorHealth 30
    $Stable = $HealthOk -and (Test-BirdMonitorStability 10)
}

$Task = Get-ScheduledTask -TaskName $TaskName
Write-Host "Estado de la tarea: $($Task.State)"
Write-Host (
    "Inicio con bateria: " +
    (-not $Task.Settings.DisallowStartIfOnBatteries)
)

if (-not $HealthOk -or -not $Stable -or $Task.State -ne "Running") {
    Write-Host "Ultimas lineas del log:" -ForegroundColor Yellow
    if (Test-Path -LiteralPath $BackendLog) {
        Get-Content -LiteralPath $BackendLog -Tail 30
    }
    throw "El backend no ha superado la comprobacion tras reconstruir la tarea."
}

Write-Host "Backend BirdMonitor operativo y protegido." -ForegroundColor Green
Write-Host "Health: http://127.0.0.1:$BackendPort/health"

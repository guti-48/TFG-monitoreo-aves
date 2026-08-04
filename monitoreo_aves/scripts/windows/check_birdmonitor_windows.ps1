Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " BirdMonitor Status Check" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$InstallScript = Join-Path $ProjectDir "scripts\windows\install_birdmonitor_windows.ps1"
$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
$StreamNodeName = if ($env:BIRDMONITOR_NODE_NAME) { $env:BIRDMONITOR_NODE_NAME } else { "birdmonitor" }
$StreamName = if ($env:BIRDMONITOR_STREAM_PATH) { $env:BIRDMONITOR_STREAM_PATH } elseif ($env:BIRDMONITOR_STREAM_NAME) { $env:BIRDMONITOR_STREAM_NAME } else { "$StreamNodeName-audio" }
$BackendPort = if ($env:BIRDMONITOR_BACKEND_PORT) { $env:BIRDMONITOR_BACKEND_PORT } else { "8000" }
$MediaMtxHlsPort = if ($env:BIRDMONITOR_MEDIAMTX_HLS_PORT) { $env:BIRDMONITOR_MEDIAMTX_HLS_PORT } else { "8888" }
$BackendBaseUrl = if ($env:BIRDMONITOR_LOCAL_BACKEND_URL) { $env:BIRDMONITOR_LOCAL_BACKEND_URL.TrimEnd("/") } else { "http://127.0.0.1:$BackendPort" }
$BackendEnv = Join-Path $ProjectDir "backend\birdmonitor.env"
$EnvValues = @{}
if (Test-Path -LiteralPath $BackendEnv) {
    foreach ($RawLine in Get-Content -LiteralPath $BackendEnv) {
        if ($RawLine -match "^\s*([^#][^=]*)=(.*)$") {
            $EnvValues[$Matches[1].Trim()] = $Matches[2].Trim()
        }
    }
}
$HlsBaseUrl = if ($EnvValues["BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL"]) {
    $EnvValues["BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL"].TrimEnd("/")
} else {
    "http://127.0.0.1:$MediaMtxHlsPort"
}
$NetworkMode = $EnvValues["BIRDMONITOR_NETWORK_MODE"]
$ServerHost = $EnvValues["BIRDMONITOR_SERVER_HOST"]
$HlsUrl = "$HlsBaseUrl/$StreamName/index.m3u8"
$ProxyCredentials = (
    $EnvValues["BIRDMONITOR_STREAM_PROXY_USER"] + ":" +
    $EnvValues["BIRDMONITOR_STREAM_PROXY_PASSWORD"]
)
$ProxyAuthorization = "Basic " + [Convert]::ToBase64String(
    [Text.Encoding]::ASCII.GetBytes($ProxyCredentials)
)
$mediaMtxIsRunning = $false
$mediaMtxPortOpen = $false
$missingScheduledTasks = $false
$scheduledTaskQueryFailed = $false

function Test-TcpPort {
    param(
        [string]$HostName,
        [int]$Port,
        [int]$TimeoutMs = 1000
    )

    $client = New-Object System.Net.Sockets.TcpClient

    try {
        $connection = $client.BeginConnect($HostName, $Port, $null, $null)

        if (-not $connection.AsyncWaitHandle.WaitOne($TimeoutMs, $false)) {
            return $false
        }

        $client.EndConnect($connection)
        return $client.Connected
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

Write-Host "Procesos MediaMTX:" -ForegroundColor Yellow
$mediaMtxProcess = Get-Process mediamtx -ErrorAction SilentlyContinue
if ($mediaMtxProcess) {
    $mediaMtxIsRunning = $true
    $mediaMtxProcess
} else {
    Write-Host "MediaMTX no esta en ejecucion." -ForegroundColor Red
}

Write-Host ""
Write-Host "Puerto $MediaMtxHlsPort MediaMTX:" -ForegroundColor Yellow
netstat -ano | findstr ":$MediaMtxHlsPort"
$mediaMtxPortOpen = Test-TcpPort -HostName "127.0.0.1" -Port ([int]$MediaMtxHlsPort)
$unexpectedHlsListener = Get-NetTCPConnection `
    -LocalPort ([int]$MediaMtxHlsPort) `
    -State Listen `
    -ErrorAction SilentlyContinue |
    Where-Object { $_.LocalAddress -notin @("127.0.0.1", "::1") }
if ($unexpectedHlsListener) {
    Write-Host "ALERTA: HLS esta expuesto fuera de loopback." -ForegroundColor Red
} elseif ($mediaMtxPortOpen) {
    Write-Host "HLS limitado correctamente a loopback." -ForegroundColor Green
}

Write-Host ""
Write-Host "Puerto $BackendPort Backend:" -ForegroundColor Yellow
netstat -ano | findstr ":$BackendPort"

Write-Host ""
Write-Host "Perfil de red:" -ForegroundColor Yellow
Write-Host "Modo: $NetworkMode"
Write-Host "IP servidor: $ServerHost"
$rtspListeners = Get-NetTCPConnection `
    -LocalPort 8554 `
    -State Listen `
    -ErrorAction SilentlyContinue
if (
    $NetworkMode -in @("local", "tailscale") -and
    @($rtspListeners).Count -eq 1 -and
    $rtspListeners.LocalAddress -eq $ServerHost
) {
    Write-Host "RTSP limitado a ${ServerHost}:8554." -ForegroundColor Green
} else {
    Write-Host "ALERTA: RTSP no coincide con el perfil de red." -ForegroundColor Red
}

$firewallRules = Get-NetFirewallRule `
    -Group "BirdMonitor" `
    -ErrorAction SilentlyContinue
if (@($firewallRules).Count -eq 2) {
    Write-Host "Firewall BirdMonitor: 2 reglas activas." -ForegroundColor Green
} else {
    Write-Host (
        "Aviso: ejecuta apply_network_mode.ps1 para crear las reglas " +
        "de Firewall."
    ) -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Tarea MediaMTX:" -ForegroundColor Yellow
$mediaTask = $null
$mediaTaskInfo = $null

try {
    $mediaTask = Get-ScheduledTask -TaskName "BirdMonitor MediaMTX" -ErrorAction Stop
    $mediaTaskInfo = Get-ScheduledTaskInfo -TaskName "BirdMonitor MediaMTX" -ErrorAction Stop
} catch [Microsoft.Management.Infrastructure.CimException] {
    if ($_.Exception.Message -match "Acceso denegado|Access is denied") {
        $scheduledTaskQueryFailed = $true
        Write-Host "No hay permisos para consultar esta tarea. Ejecuta este diagnostico como administrador." -ForegroundColor Yellow
    }
}

if ($mediaTask -and $mediaTaskInfo) {
    $mediaTask | Select-Object TaskName,State | Format-List
    $mediaTaskInfo | Format-List LastRunTime,LastTaskResult
    $MediaAction = @($mediaTask.Actions)[0]
    $MediaUsesHiddenRunner = (
        $MediaAction.Execute -match "(?i)wscript(?:\.exe)?$" -and
        $MediaAction.Arguments -like "*run_powershell_hidden.vbs*" -and
        $MediaAction.Arguments -like "*start_mediamtx*"
    )
    if ($MediaUsesHiddenRunner) {
        Write-Host (
            "MediaMTX en segundo plano: lanzador sin consola correcto."
        ) -ForegroundColor Green
    } else {
        Write-Host (
            "ALERTA: MediaMTX usa un lanzador antiguo o visible. " +
            "Ejecuta apply_network_mode.ps1 como administrador."
        ) -ForegroundColor Red
    }
} elseif (-not $scheduledTaskQueryFailed) {
    $missingScheduledTasks = $true
    Write-Host "No existe la tarea BirdMonitor MediaMTX." -ForegroundColor Red
}

Write-Host ""
Write-Host "Tarea Backend:" -ForegroundColor Yellow
$backendTask = $null
$backendTaskInfo = $null
$backendTaskQueryFailed = $false

try {
    $backendTask = Get-ScheduledTask -TaskName "BirdMonitor Backend" -ErrorAction Stop
    $backendTaskInfo = Get-ScheduledTaskInfo -TaskName "BirdMonitor Backend" -ErrorAction Stop
} catch [Microsoft.Management.Infrastructure.CimException] {
    if ($_.Exception.Message -match "Acceso denegado|Access is denied") {
        $scheduledTaskQueryFailed = $true
        $backendTaskQueryFailed = $true
        Write-Host "No hay permisos para consultar esta tarea. Ejecuta este diagnostico como administrador." -ForegroundColor Yellow
    }
}

if ($backendTask -and $backendTaskInfo) {
    $backendTask | Select-Object TaskName,State | Format-List
    $backendTaskInfo | Format-List LastRunTime,LastTaskResult
    $BackendAction = @($backendTask.Actions)[0]
    $UsesHiddenRunner = (
        $BackendAction.Execute -match "(?i)wscript(?:\.exe)?$" -and
        $BackendAction.Arguments -like "*run_powershell_hidden.vbs*" -and
        $BackendAction.Arguments -like "*run_backend_hidden.ps1*"
    )
    if ($UsesHiddenRunner) {
        Write-Host (
            "Backend en segundo plano: lanzador sin consola correcto."
        ) -ForegroundColor Green
    } else {
        Write-Host (
            "ALERTA: la tarea usa un lanzador antiguo o visible. " +
            "Ejecuta repair_backend_task.ps1 como administrador."
        ) -ForegroundColor Red
    }

    if ($backendTaskInfo.LastTaskResult -eq 267009) {
        Write-Host "La tarea Backend sigue en ejecucion. Esto es normal si uvicorn esta levantado por la tarea programada." -ForegroundColor Green
    } elseif ($backendTaskInfo.LastTaskResult -ne 0) {
        Write-Host "Aviso: LastTaskResult distinto de 0. Si el backend responde, normalmente significa que la tarea intento arrancar otra instancia con el puerto 8000 ocupado." -ForegroundColor Yellow
    }
} elseif (-not $backendTaskQueryFailed) {
    $missingScheduledTasks = $true
    Write-Host "No existe la tarea BirdMonitor Backend." -ForegroundColor Red
}

Write-Host ""
Write-Host "Prueba backend /health:" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$BackendBaseUrl/health" -UseBasicParsing -TimeoutSec 5
    Write-Host "Backend responde correctamente. Codigo: $($response.StatusCode)" -ForegroundColor Green
    Write-Host $response.Content
    $health = $response.Content | ConvertFrom-Json
    if (
        $health.network_mode -ne $NetworkMode -or
        $health.network_configured -ne $true
    ) {
        Write-Host "ALERTA: el backend no confirma el perfil de red." -ForegroundColor Red
    }
} catch {
    Write-Host "No se pudo conectar con el backend." -ForegroundColor Red
}

Write-Host ""
Write-Host "Prueba HLS interno MediaMTX:" -ForegroundColor Yellow
Write-Host $HlsUrl

try {
    $response = Invoke-WebRequest `
        -Uri $HlsUrl `
        -Headers @{ Authorization = $ProxyAuthorization } `
        -UseBasicParsing `
        -TimeoutSec 5
    Write-Host "Manifest HLS disponible. Codigo: $($response.StatusCode)" -ForegroundColor Green
} catch {
    if (-not $mediaMtxIsRunning -or -not $mediaMtxPortOpen) {
        Write-Host "MediaMTX no esta disponible en el puerto $MediaMtxHlsPort. Revisa la tarea BirdMonitor MediaMTX o ejecuta Start-ScheduledTask -TaskName `"BirdMonitor MediaMTX`"." -ForegroundColor Red
    } else {
        Write-Host "MediaMTX esta levantado, pero el manifest HLS no esta disponible." -ForegroundColor Yellow
        Write-Host "Esto suele significar que la Raspberry todavia no esta publicando audio en '$StreamName' o que birdstream.service no esta activo." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Logs:" -ForegroundColor Yellow
Write-Host $RuntimeDir

if (Test-Path $RuntimeDir) {
    Get-ChildItem $RuntimeDir
}

if ($missingScheduledTasks) {
    Write-Host ""
    Write-Host "Reparacion necesaria:" -ForegroundColor Yellow
    Write-Host "Abre PowerShell como administrador y ejecuta una sola vez:" -ForegroundColor Yellow
    Write-Host "powershell.exe -ExecutionPolicy Bypass -File `"$InstallScript`"" -ForegroundColor White
}

if ($scheduledTaskQueryFailed) {
    Write-Host ""
    Write-Host "La consulta de tareas quedo incompleta por permisos; los procesos y puertos anteriores si se comprobaron." -ForegroundColor Yellow
}

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
$HlsBaseUrl = if ($env:BIRDMONITOR_STREAM_BASE_URL) { $env:BIRDMONITOR_STREAM_BASE_URL.TrimEnd("/") } else { "http://127.0.0.1:$MediaMtxHlsPort" }
$HlsUrl = "$HlsBaseUrl/$StreamName/index.m3u8"
$StreamControlUrl = "$BackendBaseUrl/stream/control?node_name=$StreamNodeName"
$streamState = $null
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

Write-Host ""
Write-Host "Puerto $BackendPort Backend:" -ForegroundColor Yellow
netstat -ano | findstr ":$BackendPort"

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
Write-Host "Prueba backend /devices/:" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri "$BackendBaseUrl/devices/" -UseBasicParsing -TimeoutSec 5
    Write-Host "Backend responde correctamente. Codigo: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "No se pudo conectar con el backend." -ForegroundColor Red
}

Write-Host ""
Write-Host "Prueba backend /stream/control para nodo '$StreamNodeName':" -ForegroundColor Yellow

try {
    $response = Invoke-WebRequest -Uri $StreamControlUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "Control de stream responde correctamente. Codigo: $($response.StatusCode)" -ForegroundColor Green
    Write-Host $response.Content
    $streamState = $response.Content | ConvertFrom-Json
} catch {
    Write-Host "No se pudo consultar /stream/control." -ForegroundColor Red
}

Write-Host ""
Write-Host "Prueba HLS MediaMTX:" -ForegroundColor Yellow
Write-Host $HlsUrl

try {
    $response = Invoke-WebRequest -Uri $HlsUrl -UseBasicParsing -TimeoutSec 5
    Write-Host "Manifest HLS disponible. Codigo: $($response.StatusCode)" -ForegroundColor Green
} catch {
    if (-not $mediaMtxIsRunning -or -not $mediaMtxPortOpen) {
        Write-Host "MediaMTX no esta disponible en el puerto $MediaMtxHlsPort. Revisa la tarea BirdMonitor MediaMTX o ejecuta Start-ScheduledTask -TaskName `"BirdMonitor MediaMTX`"." -ForegroundColor Red
    } elseif ($streamState -and $streamState.actual_running) {
        Write-Host "MediaMTX esta levantado, pero el manifest HLS no esta disponible." -ForegroundColor Yellow
        Write-Host "El backend cree que birdstream.service esta activo, asi que revisa en la Raspberry que ese servicio este publicando hacia MediaMTX con el path '$StreamName'." -ForegroundColor Yellow
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

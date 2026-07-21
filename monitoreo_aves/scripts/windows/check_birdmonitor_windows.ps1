Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " BirdMonitor Status Check" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

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
$mediaMtxPortOpen = $null -ne (Get-NetTCPConnection -LocalPort $MediaMtxHlsPort -State Listen -ErrorAction SilentlyContinue)

Write-Host ""
Write-Host "Puerto $BackendPort Backend:" -ForegroundColor Yellow
netstat -ano | findstr ":$BackendPort"

Write-Host ""
Write-Host "Tarea MediaMTX:" -ForegroundColor Yellow
$mediaTaskInfo = Get-ScheduledTaskInfo -TaskName "BirdMonitor MediaMTX" -ErrorAction SilentlyContinue
if ($mediaTaskInfo) {
    $mediaTaskInfo | Format-List LastRunTime,LastTaskResult
} else {
    Write-Host "No existe la tarea BirdMonitor MediaMTX." -ForegroundColor Red
}

Write-Host ""
Write-Host "Tarea Backend:" -ForegroundColor Yellow
$backendTaskInfo = Get-ScheduledTaskInfo -TaskName "BirdMonitor Backend" -ErrorAction SilentlyContinue
if ($backendTaskInfo) {
    $backendTaskInfo | Format-List LastRunTime,LastTaskResult

    if ($backendTaskInfo.LastTaskResult -eq 267009) {
        Write-Host "La tarea Backend sigue en ejecucion. Esto es normal si uvicorn esta levantado por la tarea programada." -ForegroundColor Green
    } elseif ($backendTaskInfo.LastTaskResult -ne 0) {
        Write-Host "Aviso: LastTaskResult distinto de 0. Si el backend responde, normalmente significa que la tarea intento arrancar otra instancia con el puerto 8000 ocupado." -ForegroundColor Yellow
    }
} else {
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
Write-Host ""
Write-Host "======================================" -ForegroundColor Cyan
Write-Host " BirdMonitor Status Check" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host ""

$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
$StreamName = "birdmonitor-audio"
$HlsUrl = "http://127.0.0.1:8888/$StreamName/index.m3u8"
$StreamControlUrl = "http://127.0.0.1:8000/stream/control?node_name=birdmonitor"
$streamState = $null

Write-Host "Procesos MediaMTX:" -ForegroundColor Yellow
$mediaMtxProcess = Get-Process mediamtx -ErrorAction SilentlyContinue
if ($mediaMtxProcess) {
    $mediaMtxProcess
} else {
    Write-Host "MediaMTX no esta en ejecucion." -ForegroundColor Red
}

Write-Host ""
Write-Host "Puerto 8888 MediaMTX:" -ForegroundColor Yellow
netstat -ano | findstr ":8888"

Write-Host ""
Write-Host "Puerto 8000 Backend:" -ForegroundColor Yellow
netstat -ano | findstr ":8000"

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
    $response = Invoke-WebRequest -Uri "http://127.0.0.1:8000/devices/" -UseBasicParsing -TimeoutSec 5
    Write-Host "Backend responde correctamente. Codigo: $($response.StatusCode)" -ForegroundColor Green
} catch {
    Write-Host "No se pudo conectar con el backend." -ForegroundColor Red
}

Write-Host ""
Write-Host "Prueba backend /stream/control:" -ForegroundColor Yellow

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
    Write-Host "MediaMTX esta levantado, pero el manifest HLS no esta disponible." -ForegroundColor Yellow

    if ($streamState -and $streamState.actual_running) {
        Write-Host "El backend cree que birdstream.service esta activo, asi que revisa en la Raspberry que ese servicio este publicando hacia MediaMTX con el path '$StreamName'." -ForegroundColor Yellow
    } else {
        Write-Host "Esto suele significar que la Raspberry todavia no esta publicando audio en '$StreamName' o que birdstream.service no esta activo." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Logs:" -ForegroundColor Yellow
Write-Host $RuntimeDir

if (Test-Path $RuntimeDir) {
    Get-ChildItem $RuntimeDir
}
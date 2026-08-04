#requires -RunAsAdministrator

$ErrorActionPreference = "Stop"

$BackendTaskName = "BirdMonitor Backend"
$MediaMtxTaskName = "BirdMonitor MediaMTX"
$BackendPort = 8000
$HlsPort = 8888
$StreamPath = "birdmonitor-audio"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$BackendEnv = Join-Path $ProjectDir "backend\birdmonitor.env"
$EnvValues = @{}
foreach ($RawLine in Get-Content -LiteralPath $BackendEnv) {
    if ($RawLine -match "^\s*([^#][^=]*)=(.*)$") {
        $EnvValues[$Matches[1].Trim()] = $Matches[2].Trim()
    }
}
$ProxyCredentials = (
    $EnvValues["BIRDMONITOR_STREAM_PROXY_USER"] + ":" +
    $EnvValues["BIRDMONITOR_STREAM_PROXY_PASSWORD"]
)
$ProxyAuthorization = "Basic " + [Convert]::ToBase64String(
    [Text.Encoding]::ASCII.GetBytes($ProxyCredentials)
)


function Get-ListenerProcessIds {
    param([int]$Port)

    return @(
        Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
    )
}


function Stop-BackendListener {
    foreach ($processId in (Get-ListenerProcessIds -Port $BackendPort)) {
        $processInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
        $commandLine = [string]$processInfo.CommandLine

        if ($commandLine -notmatch "uvicorn\s+backend\.app\.main:app") {
            throw "El puerto $BackendPort pertenece a un proceso distinto de BirdMonitor: $commandLine"
        }

        Stop-Process -Id $processId -Force
    }
}


function Stop-MediaMtxListener {
    foreach ($processId in (Get-ListenerProcessIds -Port $HlsPort)) {
        $processInfo = Get-Process -Id $processId

        if ($processInfo.ProcessName -ne "mediamtx") {
            throw "El puerto $HlsPort pertenece a $($processInfo.ProcessName), no a MediaMTX."
        }

        Stop-Process -Id $processId -Force
    }
}


function Wait-HttpEndpoint {
    param(
        [string]$Url,
        [int]$Attempts = 30,
        [hashtable]$Headers = @{}
    )

    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            $response = Invoke-WebRequest `
                -Uri $Url `
                -Headers $Headers `
                -UseBasicParsing `
                -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
            # El publicador de la Raspberry puede tardar unos segundos en reconectar.
        }

        Start-Sleep -Seconds 1
    }

    return $false
}


foreach ($taskName in @($BackendTaskName, $MediaMtxTaskName)) {
    if ($null -eq (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue)) {
        throw "No existe la tarea programada '$taskName'. Ejecuta primero el instalador de Windows."
    }
}

Write-Host "Deteniendo de forma controlada BirdMonitor..." -ForegroundColor Cyan
Stop-ScheduledTask -TaskName $BackendTaskName -ErrorAction SilentlyContinue
Stop-ScheduledTask -TaskName $MediaMtxTaskName -ErrorAction SilentlyContinue
Stop-BackendListener
Stop-MediaMtxListener

Write-Host "Arrancando MediaMTX y FastAPI con la configuracion actualizada..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $MediaMtxTaskName
Start-ScheduledTask -TaskName $BackendTaskName

$backendUrl = "http://127.0.0.1:$BackendPort/health"
$hlsUrl = "http://127.0.0.1:$HlsPort/$StreamPath/index.m3u8"
$backendReady = Wait-HttpEndpoint -Url $backendUrl
$hlsReady = Wait-HttpEndpoint `
    -Url $hlsUrl `
    -Attempts 45 `
    -Headers @{ Authorization = $ProxyAuthorization }

if (-not $backendReady) {
    throw "FastAPI no ha vuelto a responder en $backendUrl."
}

if (-not $hlsReady) {
    throw "FastAPI responde, pero HLS no esta disponible en $hlsUrl. Revisa birdstream.service en la Raspberry."
}

Write-Host ""
Write-Host "BirdMonitor esta operativo." -ForegroundColor Green
Write-Host "HLS dashboard: /stream/hls/$StreamPath/index.m3u8"
Write-Host "RTSP: protegido con credenciales de lectura."
Write-Host ""
Write-Host "Desde el movil abre el dashboard con la IP LAN o Tailscale del servidor." -ForegroundColor Green

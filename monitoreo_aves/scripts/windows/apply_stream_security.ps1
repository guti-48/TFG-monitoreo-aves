# Aplica la configuracion endurecida de MediaMTX en Windows.
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
$MediaMtxExe = Join-Path $ProjectDir "tools\mediamtx\mediamtx.exe"
$SecureConfig = Join-Path $ProjectDir "tools\mediamtx\mediamtx.secure.yml"
$BackendEnv = Join-Path $ProjectDir "backend\birdmonitor.env"
$BackendRepair = Join-Path $ScriptDir "repair_backend_task.ps1"
$HiddenLauncher = Join-Path $ScriptDir "run_powershell_hidden.vbs"
$RuntimeDir = Join-Path $env:LOCALAPPDATA "BirdMonitor"
$RuntimeConfig = Join-Path $RuntimeDir "mediamtx.secure.runtime.yml"
$RunnerPath = Join-Path $RuntimeDir "start_mediamtx_secure.ps1"
$OutLog = Join-Path $RuntimeDir "mediamtx.out.log"
$ErrLog = Join-Path $RuntimeDir "mediamtx.err.log"
$TaskName = "BirdMonitor MediaMTX"

foreach ($RequiredPath in @(
    $MediaMtxExe,
    $SecureConfig,
    $BackendEnv,
    $BackendRepair,
    $HiddenLauncher
)) {
    if (-not (Test-Path -LiteralPath $RequiredPath)) {
        throw "No se encuentra el archivo requerido: $RequiredPath"
    }
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

$RequiredStreamKeys = @(
    "BIRDMONITOR_STREAM_PUBLISH_USER",
    "BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH",
    "BIRDMONITOR_STREAM_READER_USER",
    "BIRDMONITOR_STREAM_READER_PASSWORD",
    "BIRDMONITOR_STREAM_PROXY_USER",
    "BIRDMONITOR_STREAM_PROXY_PASSWORD"
)
foreach ($Key in $RequiredStreamKeys) {
    if (-not $EnvValues[$Key]) {
        throw (
            "Falta $Key. Ejecuta primero " +
            "python scripts/configure_stream_security.py."
        )
    }
}

$NetworkMode = $EnvValues["BIRDMONITOR_NETWORK_MODE"]
$ServerHost = $EnvValues["BIRDMONITOR_SERVER_HOST"]
if ($NetworkMode -notin @("local", "tailscale") -or -not $ServerHost) {
    throw (
        "Configura primero el modo de red con " +
        "python scripts/configure_network_mode.py --mode local|tailscale."
    )
}
$ParsedServerAddress = $null
if (-not [Net.IPAddress]::TryParse(
    $ServerHost,
    [ref]$ParsedServerAddress
)) {
    throw "BIRDMONITOR_SERVER_HOST debe ser una direccion IP."
}
$LocalServerAddress = Get-NetIPAddress `
    -IPAddress $ServerHost `
    -ErrorAction SilentlyContinue
if ($null -eq $LocalServerAddress) {
    throw "La IP $ServerHost no esta asignada a este servidor."
}

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null

$EscapedExe = $MediaMtxExe.Replace("'", "''")
$SecureConfigContent = Get-Content -LiteralPath $SecureConfig -Raw
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
    $RuntimeConfig,
    $RuntimeConfigContent,
    (New-Object Text.UTF8Encoding($false))
)
$EscapedConfig = $RuntimeConfig.Replace("'", "''")
$EscapedWorkingDir = (Split-Path -Parent $MediaMtxExe).Replace("'", "''")
$EscapedOutLog = $OutLog.Replace("'", "''")
$EscapedErrLog = $ErrLog.Replace("'", "''")
$EscapedServerHost = $ServerHost.Replace("'", "''")

@"
`$ErrorActionPreference = "Stop"
`$AddressDeadline = (Get-Date).AddMinutes(3)
while (`$null -eq (Get-NetIPAddress `
    -IPAddress '$EscapedServerHost' `
    -ErrorAction SilentlyContinue
)) {
    if ((Get-Date) -ge `$AddressDeadline) {
        Write-Error (
            "La IP segura $EscapedServerHost no esta disponible " +
            "despues de esperar a la red."
        )
        exit 2
    }
    Start-Sleep -Seconds 2
}

`$Existing = Get-Process mediamtx -ErrorAction SilentlyContinue
if (`$Existing) {
    Wait-Process -Id `$Existing.Id
    exit 1
}

`$StartArgs = @{
    FilePath = '$EscapedExe'
    ArgumentList = @('$EscapedConfig')
    WorkingDirectory = '$EscapedWorkingDir'
    WindowStyle = "Hidden"
    RedirectStandardOutput = '$EscapedOutLog'
    RedirectStandardError = '$EscapedErrLog'
}
`$Process = Start-Process @StartArgs -PassThru -Wait
exit `$Process.ExitCode
"@ | Set-Content -LiteralPath $RunnerPath -Encoding UTF8

Write-Host "Deteniendo MediaMTX anterior..." -ForegroundColor Cyan
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

$ExistingProcesses = Get-CimInstance `
    Win32_Process `
    -Filter "Name = 'mediamtx.exe'" `
    -ErrorAction SilentlyContinue
foreach ($ProcessInfo in @($ExistingProcesses)) {
    $ExecutablePath = [System.IO.Path]::GetFullPath(
        $ProcessInfo.ExecutablePath
    )
    if (-not $ExecutablePath.Equals(
        [System.IO.Path]::GetFullPath($MediaMtxExe),
        [System.StringComparison]::OrdinalIgnoreCase
    )) {
        throw (
            "Hay otro MediaMTX ajeno a BirdMonitor " +
            "(PID $($ProcessInfo.ProcessId)); no se ha detenido."
        )
    }
    Stop-Process -Id $ProcessInfo.ProcessId -Force
}

Unregister-ScheduledTask `
    -TaskName $TaskName `
    -Confirm:$false `
    -ErrorAction SilentlyContinue

$TaskUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
$Action = New-ScheduledTaskAction `
    -Execute "wscript.exe" `
    -Argument "`"$HiddenLauncher`" `"$RunnerPath`"" `
    -WorkingDirectory $RuntimeDir
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
    -Description "MediaMTX endurecido para BirdMonitor" `
    -Force | Out-Null

Write-Host "Recargando backend con la configuracion nueva..." -ForegroundColor Cyan
& $BackendRepair

Write-Host "Arrancando MediaMTX endurecido..." -ForegroundColor Cyan
Start-ScheduledTask -TaskName $TaskName

$Deadline = (Get-Date).AddSeconds(30)
$RtspReady = $false
$HlsReady = $false
while ((Get-Date) -lt $Deadline -and -not ($RtspReady -and $HlsReady)) {
    $RtspReady = [bool](Get-NetTCPConnection `
        -LocalPort 8554 `
        -State Listen `
        -ErrorAction SilentlyContinue)
    $HlsReady = [bool](Get-NetTCPConnection `
        -LocalPort 8888 `
        -State Listen `
        -ErrorAction SilentlyContinue)
    if (-not ($RtspReady -and $HlsReady)) {
        Start-Sleep -Seconds 1
    }
}

if (-not ($RtspReady -and $HlsReady)) {
    Get-Content -LiteralPath $OutLog -Tail 30 -ErrorAction SilentlyContinue
    Get-Content -LiteralPath $ErrLog -Tail 30 -ErrorAction SilentlyContinue
    throw "MediaMTX no ha abierto los puertos esperados."
}

$RtspListeners = Get-NetTCPConnection `
    -LocalPort 8554 `
    -State Listen
$UnexpectedRtspListener = $RtspListeners | Where-Object {
    $_.LocalAddress -ne $ServerHost
}
if ($UnexpectedRtspListener) {
    throw (
        "RTSP no esta limitado a la IP del modo ${NetworkMode}: " +
        $ServerHost
    )
}

$HlsListeners = Get-NetTCPConnection `
    -LocalPort 8888 `
    -State Listen
$UnexpectedHlsListener = $HlsListeners | Where-Object {
    $_.LocalAddress -notin @("127.0.0.1", "::1")
}
if ($UnexpectedHlsListener) {
    throw "HLS sigue expuesto fuera de loopback."
}

$Health = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/health" `
    -TimeoutSec 5
if (
    $Health.status -ne "ok" -or
    $Health.network_mode -ne $NetworkMode -or
    $Health.network_configured -ne $true -or
    $Health.security_configured -ne $true -or
    $Health.stream_security_configured -ne $true
) {
    throw "El backend no confirma la seguridad completa."
}

$AnonymousHlsStatus = try {
    Invoke-WebRequest `
        -UseBasicParsing `
        -Uri (
            "http://127.0.0.1:8000/stream/hls/" +
            "diagnostico-audio/index.m3u8"
        ) `
        -TimeoutSec 5 | Out-Null
    200
} catch {
    [int]$_.Exception.Response.StatusCode
}
if ($AnonymousHlsStatus -ne 401) {
    throw (
        "El proxy HLS anonimo deberia responder 401, " +
        "pero devolvio $AnonymousHlsStatus."
    )
}

$AuthPayload = @{
    user = $EnvValues["BIRDMONITOR_STREAM_PROXY_USER"]
    password = $EnvValues["BIRDMONITOR_STREAM_PROXY_PASSWORD"]
    action = "read"
    path = "diagnostico-audio"
    protocol = "hls"
} | ConvertTo-Json
$AuthResponse = Invoke-WebRequest `
    -UseBasicParsing `
    -Method Post `
    -Uri "http://127.0.0.1:8000/internal/mediamtx/auth" `
    -ContentType "application/json" `
    -Body $AuthPayload
if ($AuthResponse.StatusCode -ne 204) {
    throw "La autenticacion interna de MediaMTX no responde correctamente."
}

$Task = Get-ScheduledTask -TaskName $TaskName
Write-Host ""
Write-Host "Streaming protegido aplicado correctamente." -ForegroundColor Green
Write-Host "Modo de red: $NetworkMode ($ServerHost)"
Write-Host "Tarea MediaMTX: $($Task.State)"
Write-Host "RTSP publicacion: protegido en ${ServerHost}:8554"
Write-Host "HLS interno: 127.0.0.1:8888"
Write-Host "HLS del dashboard: /stream/hls/... (requiere sesion)"

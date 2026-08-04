# Aplica el perfil de red y el Firewall de BirdMonitor en Windows.
# Ejecutar desde PowerShell como administrador despues de
# scripts/configure_network_mode.py.

$ErrorActionPreference = "Stop"

$CurrentUser = [Security.Principal.WindowsIdentity]::GetCurrent()
$PrincipalCheck = New-Object Security.Principal.WindowsPrincipal($CurrentUser)
if (-not $PrincipalCheck.IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)) {
    throw "Abre PowerShell como administrador y vuelve a ejecutar el script."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Resolve-Path (Join-Path $ScriptDir "..\..")).Path
$BackendEnv = Join-Path $ProjectDir "backend\birdmonitor.env"
$ApplyStreaming = Join-Path $ScriptDir "apply_stream_security.ps1"
$FirewallGroup = "BirdMonitor"

foreach ($RequiredPath in @($BackendEnv, $ApplyStreaming)) {
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

$NetworkMode = $EnvValues["BIRDMONITOR_NETWORK_MODE"]
$ServerHost = $EnvValues["BIRDMONITOR_SERVER_HOST"]
if ($NetworkMode -notin @("local", "tailscale") -or -not $ServerHost) {
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

$RuleCommon = @{
    Group = $FirewallGroup
    Direction = "Inbound"
    Action = "Allow"
    Enabled = "True"
    Protocol = "TCP"
    LocalAddress = $ServerHost
    Profile = "Any"
    EdgeTraversalPolicy = "Block"
}

if ($NetworkMode -eq "tailscale") {
    $TailscaleAdapter = Get-NetAdapter -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Status -eq "Up" -and
            (
                $_.Name -like "*Tailscale*" -or
                $_.InterfaceDescription -like "*Tailscale*"
            )
        } |
        Select-Object -First 1
    if ($null -eq $TailscaleAdapter) {
        throw (
            "El modo Tailscale requiere el adaptador Tailscale activo " +
            "en el servidor."
        )
    }
    # El servidor se enlaza a la IPv4 Tailscale elegida. Mantener la regla
    # en la misma familia evita configuraciones ambiguas o no admitidas al
    # combinar LocalAddress IPv4 con redes remotas IPv6.
    $RuleCommon["RemoteAddress"] = "100.64.0.0/10"
    $RuleCommon["InterfaceAlias"] = $TailscaleAdapter.Name
    $ModeDescription = (
        "Solo tailnet por el adaptador $($TailscaleAdapter.Name)"
    )
} else {
    $RuleCommon["RemoteAddress"] = "LocalSubnet"
    $ModeDescription = "Solo equipos de la subred local"
}

Write-Host "Aplicando reglas de Firewall BirdMonitor..." -ForegroundColor Cyan
Get-NetFirewallRule `
    -Group $FirewallGroup `
    -ErrorAction SilentlyContinue |
    Remove-NetFirewallRule

New-NetFirewallRule `
    @RuleCommon `
    -Name "BirdMonitor-Dashboard-$NetworkMode" `
    -DisplayName "BirdMonitor Dashboard ($NetworkMode)" `
    -Description "$ModeDescription; sesion web obligatoria." `
    -LocalPort 8000 | Out-Null

New-NetFirewallRule `
    @RuleCommon `
    -Name "BirdMonitor-RTSP-$NetworkMode" `
    -DisplayName "BirdMonitor RTSP ($NetworkMode)" `
    -Description "$ModeDescription; publicacion RTSP autenticada." `
    -LocalPort 8554 | Out-Null

Write-Host "Recargando servicios con el perfil elegido..." -ForegroundColor Cyan
& $ApplyStreaming

$Health = Invoke-RestMethod `
    -Uri "http://127.0.0.1:8000/health" `
    -TimeoutSec 5
if (
    $Health.network_mode -ne $NetworkMode -or
    $Health.network_configured -ne $true
) {
    throw "El backend no confirma el modo de red $NetworkMode."
}

$RtspListener = Get-NetTCPConnection `
    -LocalPort 8554 `
    -State Listen
if (
    @($RtspListener).Count -ne 1 -or
    $RtspListener.LocalAddress -ne $ServerHost
) {
    throw "RTSP no esta limitado a ${ServerHost}:8554."
}

Write-Host ""
Write-Host "Modo de red aplicado correctamente." -ForegroundColor Green
Write-Host "Modo: $NetworkMode"
Write-Host "Dashboard: http://${ServerHost}:8000"
Write-Host "RTSP: ${ServerHost}:8554"
Write-Host "HLS: 127.0.0.1:8888 (interno)"
Get-NetFirewallRule -Group $FirewallGroup |
    Select-Object DisplayName,Enabled,Profile |
    Format-Table -AutoSize

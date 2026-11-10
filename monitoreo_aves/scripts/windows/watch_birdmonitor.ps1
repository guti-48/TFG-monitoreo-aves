# Comprobacion finita: el Programador la repite, tambien despues de reanudar.
# No cambia la red, el Firewall ni las credenciales. -LibraryOnly es para tests.
param([switch]$LibraryOnly)
$ErrorActionPreference = 'Stop'

function Get-RecoveryDecision {
    param([string]$State, [string]$Health, [int]$Failures, [double]$AgeSeconds)
    if ($State -in @('Missing', 'Disabled') -or $Health -ne 'Unreachable') { return 'None' }
    # Respeta el tiempo de arranque y los reintentos propios del Programador.
    if ($AgeSeconds -lt 180 -or $Failures -lt 2) { return 'None' }
    return 'Recover'
}

function Get-BackendHealth {
    param([string]$Uri)
    try {
        $Result = Invoke-RestMethod -Uri $Uri -TimeoutSec 5
        if ($Result.status -eq 'ok') { return 'Healthy' }
        return 'Configuration'
    } catch {
        # Un 401/403/503 es una respuesta, no un proceso colgado.
        if ($null -ne $_.Exception.Response) { return 'Configuration' }
        return 'Unreachable'
    }
}

function Test-LocalAddress {
    param([string]$Address)
    $Addresses = [Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
        Where-Object { $_.OperationalStatus -eq 'Up' } |
        ForEach-Object { $_.GetIPProperties().UnicastAddresses } |
        ForEach-Object { $_.Address.IPAddressToString }
    return $Addresses -contains $Address
}

function Test-ListeningPort {
    param([string]$Address, [int]$Port)
    $Client = New-Object Net.Sockets.TcpClient
    try {
        $Pending = $Client.BeginConnect($Address, $Port, $null, $null)
        if (-not $Pending.AsyncWaitHandle.WaitOne(1000)) { return $false }
        $Client.EndConnect($Pending)
        return $true
    } catch { return $false }
    finally { $Client.Close() }
}

function Test-OwnedProcess {
    param($Process, [string]$Executable, [string]$CommandPattern)
    if ($null -eq $Process -or $Process.CommandLine -notmatch $CommandPattern) { return $false }
    if ($Process.ExecutablePath -eq $Executable) { return $true }
    # En Windows el python.exe del venv es un redirector. El socket pertenece
    # al Python base, hijo del redirector: exigir la ascendencia de ESTE venv.
    $LaunchPrefix = '^"?' + [regex]::Escape($Executable) + '"?\s'
    if ([IO.Path]::GetFileName($Executable) -ne 'python.exe' -or
        -not $Process.ParentProcessId -or $Process.CommandLine -notmatch $LaunchPrefix) { return $false }
    $Parent = Get-CimInstance Win32_Process -Filter "ProcessId = $($Process.ParentProcessId)"
    return ($null -ne $Parent -and $Parent.ExecutablePath -eq $Executable -and
        $Parent.CommandLine -match $CommandPattern -and $Parent.CreationDate -le $Process.CreationDate)
}

function Test-TaskOwner {
    param([string]$UserId, [string]$ExpectedSid)
    try {
        if ($UserId -match '^S-1-') { return $UserId -eq $ExpectedSid }
        $Account = New-Object Security.Principal.NTAccount($UserId)
        return $Account.Translate([Security.Principal.SecurityIdentifier]).Value -eq $ExpectedSid
    } catch { return $false }
}

function Write-RecoveryLog {
    param([string]$Message)
    $Log = Join-Path $RuntimeDir 'recovery.log'
    if ((Test-Path -LiteralPath $Log) -and (Get-Item -LiteralPath $Log).Length -gt 1MB) {
        Move-Item -LiteralPath $Log -Destination "$Log.1" -Force
    }
    Add-Content -LiteralPath $Log -Encoding UTF8 -Value "$(Get-Date -Format o) $Message"
}

function Restore-BirdMonitorTask {
    param($Task, [string]$Executable, [string]$CommandPattern, [int[]]$Ports)
    # Solo las tareas creadas por esta instalacion y del usuario actual.
    $ExpectedAction = '"' + $HiddenLauncher + '" "' + $ExpectedRunner + '"'
    if (@($Task.Actions).Count -ne 1 -or $Task.Actions[0].Execute -ne 'wscript.exe' -or
        $Task.Actions[0].Arguments -ne $ExpectedAction -or
        -not (Test-TaskOwner $Task.Principal.UserId $CurrentIdentity.User.Value)) {
        Write-RecoveryLog "$($Task.TaskName): accion o propietario no reconocido; no se modifica."
        return
    }
    # Si un puerto pertenece a otra aplicacion, nunca detenerla ni duplicarla.
    $Listeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop |
        Where-Object { $_.LocalPort -in $Ports })
    foreach ($Listener in $Listeners) {
        $Owner = Get-CimInstance Win32_Process -Filter "ProcessId = $($Listener.OwningProcess)"
        if (-not (Test-OwnedProcess $Owner $Executable $CommandPattern)) {
            Write-RecoveryLog "$($Task.TaskName): puerto ocupado por un proceso ajeno; no se modifica."
            return
        }
    }
    # Conserva las identidades antes de parar la tarea, por si quedan hijos.
    $Candidates = @(Get-CimInstance Win32_Process | Where-Object {
        Test-OwnedProcess $_ $Executable $CommandPattern
    })
    Stop-ScheduledTask -InputObject $Task
    foreach ($Candidate in $Candidates) {
        $StillRunning = Get-CimInstance Win32_Process -Filter "ProcessId = $($Candidate.ProcessId)"
        # La tarea puede haber terminado el redirector padre. Revalidar la
        # identidad previamente autorizada, no depender de que el padre siga vivo.
        if ($null -ne $StillRunning -and
            $StillRunning.CreationDate -eq $Candidate.CreationDate -and
            $StillRunning.ExecutablePath -eq $Candidate.ExecutablePath -and
            $StillRunning.CommandLine -eq $Candidate.CommandLine) {
            Stop-Process -Id $Candidate.ProcessId -Force
        }
    }
    Start-ScheduledTask -TaskName $Task.TaskName
    Write-RecoveryLog "$($Task.TaskName): reinicio solicitado tras dos comprobaciones fallidas."
}

function Invoke-BirdMonitorWatch {
    $ScriptDir = $PSScriptRoot
    $ProjectDir = (Resolve-Path (Join-Path $ScriptDir '..\..')).Path
    $RuntimeDir = Join-Path $env:LOCALAPPDATA 'BirdMonitor'
    $HiddenLauncher = Join-Path $ScriptDir 'run_powershell_hidden.vbs'
    $CurrentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
    # Lock compartido entre invocacion manual y tarea. No solapa dos reparaciones.
    try {
        $Lock = [IO.File]::Open((Join-Path $RuntimeDir 'recovery.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    } catch [IO.IOException] { return }
    try {
        $Config = @{}
        foreach ($Line in Get-Content -LiteralPath (Join-Path $ProjectDir 'backend\birdmonitor.env')) {
            if ($Line -match '^\s*(BIRDMONITOR_(?:SERVER_HOST|BACKEND_HOST|BACKEND_PORT))\s*=(.*)$') {
                $Config[$Matches[1]] = $Matches[2].Trim().Trim('"').Trim("'")
            }
        }
        $Port = 8000
        if ($Config.BIRDMONITOR_BACKEND_PORT) { $Port = [int]$Config.BIRDMONITOR_BACKEND_PORT }
        if ($env:BIRDMONITOR_BACKEND_PORT) { $Port = [int]$env:BIRDMONITOR_BACKEND_PORT }
        $Bind = $Config.BIRDMONITOR_BACKEND_HOST
        if ($env:BIRDMONITOR_BACKEND_HOST) { $Bind = $env:BIRDMONITOR_BACKEND_HOST }
        $ProbeHost = if (-not $Bind -or $Bind -eq '0.0.0.0') { '127.0.0.1' } elseif ($Bind -eq '::') { '[::1]' } else { $Bind }
        $ServerHost = $Config.BIRDMONITOR_SERVER_HOST
        $NetworkReady = $ServerHost -and (Test-LocalAddress $ServerHost)
        $StatePath = Join-Path $RuntimeDir 'recovery-state.json'
        $State = @{ backend = 0; stream = 0; checked = [DateTime]::UtcNow.ToString('o') }
        try {
            $Previous = Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json
            $Gap = ([DateTime]::UtcNow - [DateTime]::Parse($Previous.checked).ToUniversalTime()).TotalSeconds
            # Tras reposo largo, comienza de nuevo el margen de recuperacion.
            if ($Gap -ge 0 -and $Gap -lt 150) {
                $State.backend = [int]$Previous.backend
                $State.stream = [int]$Previous.stream
            }
        } catch { }
        $BackendHealth = Get-BackendHealth "http://${ProbeHost}:$Port/health"
        foreach ($Kind in @('backend', 'stream')) {
            $TaskName = if ($Kind -eq 'backend') { 'BirdMonitor Backend' } else { 'BirdMonitor MediaMTX' }
            $Task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
            if (-not $Task -or $Task.State -eq 'Disabled') { $State[$Kind] = 0; continue }
            if ($Kind -eq 'backend') {
                $Health = $BackendHealth
                # Un bind explicito no puede recuperarse mientras falta su interfaz.
                if ($ProbeHost -notin @('127.0.0.1', '[::1]', 'localhost') -and -not $NetworkReady) {
                    $State[$Kind] = 0; continue
                }
                $ExpectedRunner = Join-Path $ScriptDir 'run_backend_hidden.ps1'
                $Executable = Join-Path $ProjectDir 'venv\Scripts\python.exe'
                $Pattern = '(?:^|\s)-m\s+uvicorn\s+backend\.app\.main:app(?:\s|$)'
                $Ports = @($Port)
            } else {
                # Sin IP o sin backend, esperar. La ausencia de aves/HLS no es un fallo del servidor.
                if (-not $NetworkReady -or $BackendHealth -ne 'Healthy') { $State[$Kind] = 0; continue }
                $Health = if ((Test-ListeningPort $ServerHost 8554) -and (Test-ListeningPort '127.0.0.1' 8888)) { 'Healthy' } else { 'Unreachable' }
                $ExpectedRunner = Join-Path $RuntimeDir 'start_mediamtx_secure.ps1'
                $Executable = Join-Path $ProjectDir 'tools\mediamtx\mediamtx.exe'
                $Pattern = [regex]::Escape((Join-Path $RuntimeDir 'mediamtx.secure.runtime.yml'))
                $Ports = @(8554, 8888)
            }
            if ($Health -eq 'Unreachable') { $State[$Kind]++ } else { $State[$Kind] = 0 }
            $Info = $Task | Get-ScheduledTaskInfo
            $Age = ((Get-Date) - $Info.LastRunTime).TotalSeconds
            if ((Get-RecoveryDecision $Task.State $Health $State[$Kind] $Age) -eq 'Recover') {
                Restore-BirdMonitorTask $Task $Executable $Pattern $Ports
                $State[$Kind] = 0
            }
        }
        $State | ConvertTo-Json | Set-Content -LiteralPath $StatePath -Encoding UTF8
    } catch {
        # No volcar excepciones que puedan contener configuracion privada.
        Write-RecoveryLog ('Comprobacion incompleta: ' + $_.Exception.GetType().Name)
        throw 'No se pudo completar la supervision. Consulta recovery.log.'
    } finally { $Lock.Dispose() }
}

if (-not $LibraryOnly) { Invoke-BirdMonitorWatch }

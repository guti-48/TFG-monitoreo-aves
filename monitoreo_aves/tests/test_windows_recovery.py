"""Ejecuta las decisiones de recuperacion en PowerShell, sin tocar servicios."""
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts" / "windows"
SHELL = shutil.which("powershell.exe") or shutil.which("pwsh")


def run_ps(code):
    if not SHELL:
        pytest.skip("Requiere PowerShell (sin acceso a servicios reales)")
    result = subprocess.run(
        [SHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", code],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout.strip()


@pytest.mark.parametrize("state,health,failures,age,expected", [
    ("Running", "Healthy", 9, 900, "None"),
    ("Running", "Configuration", 9, 900, "None"),
    ("Disabled", "Unreachable", 9, 900, "None"),
    ("Missing", "Unreachable", 9, 900, "None"),
    ("Running", "Unreachable", 1, 900, "None"),
    ("Running", "Unreachable", 2, 40, "None"),
    ("Queued", "Unreachable", 2, 40, "None"),
    ("Ready", "Unreachable", 2, 900, "Recover"),
    ("Running", "Unreachable", 2, 900, "Recover"),
    ("Queued", "Unreachable", 2, 900, "Recover"),
])
def test_recovery_decision(state, health, failures, age, expected):
    assert run_ps(
        ". ./scripts/windows/watch_birdmonitor.ps1 -LibraryOnly; "
        f"Get-RecoveryDecision '{state}' '{health}' {failures} {age}"
    ) == expected


def test_owned_process_requires_executable_and_module():
    assert run_ps(r'''
. ./scripts/windows/watch_birdmonitor.ps1 -LibraryOnly
$p = [pscustomobject]@{ExecutablePath='C:\project\python.exe'; CommandLine='python -m uvicorn backend.app.main:app --port 8000'}
$pattern = '(?:^|\s)-m\s+uvicorn\s+backend\.app\.main:app(?:\s|$)'
Test-OwnedProcess $p 'C:\project\python.exe' $pattern
Test-OwnedProcess $p 'C:\another\python.exe' $pattern
$p.CommandLine = 'python unrelated.py'
Test-OwnedProcess $p 'C:\project\python.exe' $pattern
Test-OwnedProcess $null 'C:\project\python.exe' $pattern
''').splitlines() == ["True", "False", "False", "False"]


def test_backend_health_with_mocked_http():
    assert run_ps(r'''
. ./scripts/windows/watch_birdmonitor.ps1 -LibraryOnly
function Invoke-RestMethod { return @{status='ok'} }
Get-BackendHealth 'http://localhost/health'
function Invoke-RestMethod { return @{status='invalid'} }
Get-BackendHealth 'http://localhost/health'
function Invoke-RestMethod { throw [System.Net.WebException]::new('offline') }
Get-BackendHealth 'http://localhost/health'
''').splitlines() == ["Healthy", "Configuration", "Unreachable"]


def test_python_venv_redirector_child_requires_verified_parent():
    assert run_ps(r'''
. ./scripts/windows/watch_birdmonitor.ps1 -LibraryOnly
$p = [pscustomobject]@{ExecutablePath='C:\base\python.exe'; CommandLine='"C:\project\python.exe" -m uvicorn backend.app.main:app'; ParentProcessId=42; CreationDate=2}
function Get-CimInstance {
    return [pscustomobject]@{ExecutablePath='C:\project\python.exe'; CommandLine='python -m uvicorn backend.app.main:app'; CreationDate=1}
}
Test-OwnedProcess $p 'C:\project\python.exe' 'uvicorn\s+backend\.app\.main:app'
function Get-CimInstance { return $null }
Test-OwnedProcess $p 'C:\project\python.exe' 'uvicorn\s+backend\.app\.main:app'
''').splitlines() == ["True", "False"]


def test_scripts_parse_in_windows_powershell():
    assert run_ps(r'''
$ErrorActionPreference = 'Stop'
Get-ChildItem scripts/windows/*.ps1 | ForEach-Object {
    $errors = $null
    $tokens = $null
    [void][Management.Automation.Language.Parser]::ParseFile($_.FullName, [ref]$tokens, [ref]$errors)
    if ($errors) { throw ($errors | Out-String) }
}
'OK'
''') == "OK"


@pytest.mark.skipif(not sys.platform.startswith('win'), reason="Identidad Windows")
def test_task_owner_accepts_short_account_name_but_not_another_sid():
    assert run_ps(r'''
. ./scripts/windows/watch_birdmonitor.ps1 -LibraryOnly
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
Test-TaskOwner $identity.Name $identity.User.Value
Test-TaskOwner ($identity.Name.Split('\')[-1]) $identity.User.Value
Test-TaskOwner $identity.User.Value $identity.User.Value
Test-TaskOwner 'S-1-5-18' $identity.User.Value
''').splitlines() == ["True", "True", "True", "False"]


@pytest.mark.parametrize('scenario,expected', [
    ('owned', ['stop-task', 'stop-process', 'start-task']),
    ('foreign-port', []),
    ('foreign-task', []),
    ('reused-pid', ['stop-task', 'start-task']),
])
def test_restore_guards_with_mocked_windows_commands(scenario, expected):
    output = run_ps(r'''
. ./scripts/windows/watch_birdmonitor.ps1 -LibraryOnly
$HiddenLauncher = 'C:\project\hidden.vbs'
$ExpectedRunner = 'C:\project\runner.ps1'
$CurrentIdentity = [pscustomobject]@{User=@{Value='S-1-5-21-123'}}
$task = [pscustomobject]@{
    TaskName='BirdMonitor Backend'
    Principal=@{UserId='S-1-5-21-123'}
    Actions=@([pscustomobject]@{Execute='wscript.exe'; Arguments='"C:\project\hidden.vbs" "C:\project\runner.ps1"'})
}
$script:calls = [Collections.Generic.List[string]]::new()
$script:lookups = 0
function Write-RecoveryLog { param($Message) }
function Get-NetTCPConnection { return [pscustomobject]@{LocalPort=8000; OwningProcess=42} }
function Get-CimInstance {
    param($ClassName, $Filter)
    $script:lookups++
    $exe = 'C:\project\python.exe'
    if ($scenario -eq 'foreign-port') { $exe = 'C:\other\python.exe' }
    $created = 1
    if ($scenario -eq 'reused-pid' -and $script:lookups -ge 3) { $created = 2 }
    return [pscustomobject]@{ExecutablePath=$exe; CommandLine='python -m uvicorn backend.app.main:app'; ProcessId=42; CreationDate=$created}
}
function Stop-ScheduledTask { param($InputObject); $script:calls.Add('stop-task') }
function Stop-Process { param($Id, [switch]$Force); $script:calls.Add('stop-process') }
function Start-ScheduledTask { param($TaskName); $script:calls.Add('start-task') }
''' + f"$scenario = '{scenario}'\n" + r'''
if ($scenario -eq 'foreign-task') { $task.Principal.UserId = 'S-1-5-21-456' }
Restore-BirdMonitorTask $task 'C:\project\python.exe' 'uvicorn\s+backend\.app\.main:app' @(8000)
$script:calls
''')
    assert output.splitlines() == expected


def test_recovery_installation_and_safety_guards():
    installer = (SCRIPTS / "install_recovery_task.ps1").read_text()
    watch = (SCRIPTS / "watch_birdmonitor.ps1").read_text()
    for name in ("repair_backend_task.ps1", "apply_stream_security.ps1"):
        assert "install_recovery_task.ps1" in (SCRIPTS / name).read_text()
    assert "BirdMonitor Recovery" in (SCRIPTS / "uninstall_birdmonitor_windows.ps1").read_text()
    assert "-RunLevel Limited" in installer
    assert "-MultipleInstances IgnoreNew" in installer
    assert "-RepetitionInterval (New-TimeSpan -Minutes 1)" in installer
    assert "-WakeToRun" not in installer
    assert "CreationDate -eq $Candidate.CreationDate" in watch
    assert "$Gap -lt 150" in watch
    assert "$BackendHealth -ne 'Healthy'" in watch
    assert "-Headers" not in watch  # No necesita ni transmite credenciales.
    assert "Restart-Service" not in watch  # No cambia Tailscale ni otros servicios.

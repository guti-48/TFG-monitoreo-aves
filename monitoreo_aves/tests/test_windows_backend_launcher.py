from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_SCRIPTS = PROJECT_ROOT / "scripts" / "windows"


def test_tareas_backend_usan_lanzador_powershell_oculto():
    repair = (WINDOWS_SCRIPTS / "repair_backend_task.ps1").read_text(
        encoding="utf-8"
    )
    installer = (
        WINDOWS_SCRIPTS / "install_birdmonitor_windows.ps1"
    ).read_text(encoding="utf-8")

    for script in (repair, installer):
        assert "run_backend_hidden.ps1" in script
        assert "run_powershell_hidden.vbs" in script
        assert '-Execute "wscript.exe"' in script
        assert '-Execute "cmd.exe"' not in script


def test_lanzador_oculto_espera_uvicorn_y_conserva_log():
    runner = (WINDOWS_SCRIPTS / "run_backend_hidden.ps1").read_text(
        encoding="utf-8"
    )

    assert "backend.app.main:app" in runner
    assert "ForEach-Object" in runner
    assert '$ErrorActionPreference = "Continue"' in runner
    assert "backend.log" in runner
    assert "exit $BackendExitCode" in runner


def test_aplicador_mediamtx_tambien_usa_lanzador_sin_consola():
    stream_installer = (
        WINDOWS_SCRIPTS / "apply_stream_security.ps1"
    ).read_text(encoding="utf-8")
    hidden_launcher = (
        WINDOWS_SCRIPTS / "run_powershell_hidden.vbs"
    ).read_text(encoding="utf-8")

    assert "run_powershell_hidden.vbs" in stream_installer
    assert '-Execute "wscript.exe"' in stream_installer
    assert "shell.Run(command, 0, True)" in hidden_launcher


def test_lanzador_mediamtx_detecta_la_ip_sin_cmdlets_privilegiados():
    stream_installer = (
        WINDOWS_SCRIPTS / "apply_stream_security.ps1"
    ).read_text(encoding="utf-8")
    full_installer = (
        WINDOWS_SCRIPTS / "install_birdmonitor_windows.ps1"
    ).read_text(encoding="utf-8")

    for script in (stream_installer, full_installer):
        assert "NetworkInterface]::GetAllNetworkInterfaces" in script
        assert "Test-BirdMonitorLocalAddress" in script

    assert "SkipBackendReload" in stream_installer

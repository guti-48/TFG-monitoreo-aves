from pathlib import Path
import subprocess
import sys

from scripts import configure_stream_security


def test_generador_es_ejecutable_desde_la_raiz_del_proyecto():
    result = subprocess.run(
        [
            sys.executable,
            str(Path("scripts") / "configure_stream_security.py"),
            "--help",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "--server-host" in result.stdout
    assert "--rotate-reader" in result.stdout


def test_actualizacion_de_env_preserva_lineas_y_no_duplica_claves():
    original = [
        "# Configuracion existente",
        "BIRDMONITOR_SECURITY_MODE=required",
        "BIRDMONITOR_STREAM_PROXY_USER=antiguo",
    ]
    updates = {
        "BIRDMONITOR_STREAM_SECURITY_MODE": "required",
        "BIRDMONITOR_STREAM_PROXY_USER": "nuevo",
    }

    result = configure_stream_security.replace_env_values(original, updates)

    assert "BIRDMONITOR_SECURITY_MODE=required" in result
    assert result.count("BIRDMONITOR_STREAM_PROXY_USER=nuevo") == 1
    assert result.count("BIRDMONITOR_STREAM_SECURITY_MODE=required") == 1

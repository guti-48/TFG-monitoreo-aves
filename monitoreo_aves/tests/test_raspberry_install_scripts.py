from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = PROJECT_ROOT / "scripts" / "raspberry_pi"


def test_instalador_crea_los_tres_servicios_sin_secretos_embebidos():
    script = (SCRIPT_DIR / "install_birdmonitor_services.sh").read_text(
        encoding="utf-8"
    )

    assert "/etc/systemd/system/birdmonitor.service" in script
    assert "/etc/systemd/system/birdstream.service" in script
    assert "/etc/systemd/system/birdmonitor-stream-supervisor.service" in script
    assert "EnvironmentFile=/etc/birdmonitor/stream-publisher.env" in script
    assert "${BIRDMONITOR_STREAM_PUBLISH_URL}" in script
    assert "command -v arecord" in script
    assert "User=root" in script
    assert "supervisor.py" in script


def test_microfono_compartido_usa_dsnoop_y_conserva_backup():
    script = (SCRIPT_DIR / "configure_shared_microphone.sh").read_text(
        encoding="utf-8"
    )

    assert "type dsnoop" in script
    assert "pcm.micshared" in script
    assert "/etc/birdmonitor/backups/asound.conf" in script
    assert "arecord -q -D plug:micshared" in script
    assert "se ha restaurado /etc/asound.conf" in script
    assert "rm -f /etc/asound.conf" in script


def test_plantilla_del_nodo_es_generica_y_usa_la_ruta_del_clon():
    template = (
        PROJECT_ROOT / "hardware" / "raspberry_pi" / "birdmonitor.env.example"
    ).read_text(encoding="utf-8")

    assert "/home/pi/birdmonitor/hardware/raspberry_pi/deployment_state.json" in template
    assert "/home/pi/birdmonitor/monitoreo_aves/" not in template
    assert "BIRDMONITOR_LEGACY_SITE_CODE=\n" in template

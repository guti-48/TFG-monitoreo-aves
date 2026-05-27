import os
import time
import subprocess
import requests
from datetime import datetime

NODE_NAME = os.getenv("BIRDMONITOR_NODE_NAME", "birdmonitor")
SERVER_URL = os.getenv("BIRDMONITOR_SERVER_URL", "http://100.98.248.58:8000").rstrip("/")

SERVICE_NAME = os.getenv("BIRDMONITOR_STREAM_SERVICE", "birdstream.service")
POLL_INTERVAL = int(os.getenv("BIRDMONITOR_STREAM_POLL_INTERVAL", "5"))

CONTROL_URL = f"{SERVER_URL}/stream/control"
STATUS_URL = f"{SERVER_URL}/stream/status"


def log(msg: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] {msg}", flush=True)


def run_systemctl(action: str) -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", action, SERVICE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20
        )

        if result.returncode != 0:
            log(f"systemctl {action} falló: {result.stderr.strip()}")
            return False

        return True

    except Exception as e:
        log(f"Error ejecutando systemctl {action}: {e}")
        return False


def is_stream_running() -> bool:
    try:
        result = subprocess.run(
            ["/usr/bin/systemctl", "is-active", "--quiet", SERVICE_NAME],
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        log(f"No se pudo consultar estado de {SERVICE_NAME}: {e}")
        return False


def get_desired_state():
    try:
        response = requests.get(
            CONTROL_URL,
            params={"node_name": NODE_NAME},
            timeout=10
        )
        response.raise_for_status()
        data = response.json()
        return bool(data.get("stream_enabled", False))

    except Exception as e:
        log(f"No se pudo consultar estado deseado en backend: {e}")
        return None


def report_status(running: bool, detail: str = "") -> None:
    try:
        requests.post(
            STATUS_URL,
            json={
                "node_name": NODE_NAME,
                "running": running,
                "detail": detail
            },
            timeout=10
        )
    except Exception as e:
        log(f"No se pudo reportar estado al backend: {e}")


def main():
    log(f"StreamSupervisor iniciado para nodo '{NODE_NAME}'")
    log(f"Backend: {SERVER_URL}")
    log(f"Servicio controlado: {SERVICE_NAME}")

    while True:
        desired = get_desired_state()
        running = is_stream_running()

        if desired is None:
            report_status(running, "Backend no disponible, se mantiene el estado actual")
            time.sleep(POLL_INTERVAL)
            continue

        if desired and not running:
            log("Backend solicita ACTIVAR streaming.")
            ok = run_systemctl("start")
            running = is_stream_running()
            report_status(running, "Streaming activado" if ok else "Error activando streaming")

        elif not desired and running:
            log("Backend solicita DETENER streaming.")
            ok = run_systemctl("stop")
            running = is_stream_running()
            report_status(running, "Streaming detenido" if ok else "Error deteniendo streaming")

        else:
            report_status(running, "Estado sincronizado")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
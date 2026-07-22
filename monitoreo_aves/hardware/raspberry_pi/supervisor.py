import os
import time
import subprocess
import requests
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_ENV_FILE = os.path.join(CURRENT_DIR, "birdmonitor.env")


def cargarEnvLocal(path):
    """Carga variables KEY=VALUE desde un archivo local sin pisar el entorno real."""
    if not os.path.isfile(path):
        return

    try:
        with open(path, "r", encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()

                if not line or line.startswith("#") or "=" not in line:
                    continue

                if line.startswith("export "):
                    line = line[len("export "):].strip()

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")

                if key:
                    os.environ.setdefault(key, value)
    except Exception as e:
        print(f"No se pudo cargar configuracion local {path}: {e}")

cargarEnvLocal(LOCAL_ENV_FILE)

NODE_NAME = os.getenv("BIRDMONITOR_NODE_NAME", "birdmonitor")
SERVER_URL = os.getenv("BIRDMONITOR_SERVER_URL", "http://127.0.0.1:8000").rstrip("/")

SERVICE_NAME = os.getenv("BIRDMONITOR_STREAM_SERVICE", "birdstream.service")


def leer_entero_entorno(nombre: str, valor_por_defecto: int, minimo: int = 1) -> int:
    try:
        return max(minimo, int(os.getenv(nombre, str(valor_por_defecto))))
    except ValueError:
        return valor_por_defecto


POLL_INTERVAL = leer_entero_entorno("BIRDMONITOR_STREAM_POLL_INTERVAL", 5)
HLS_FAILURE_LIMIT = leer_entero_entorno("BIRDMONITOR_STREAM_FAILURE_LIMIT", 3)
HLS_HEALTH_TIMEOUT = leer_entero_entorno("BIRDMONITOR_STREAM_HEALTH_TIMEOUT", 5)

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


def get_control_state():
    try:
        response = requests.get(
            CONTROL_URL,
            params={"node_name": NODE_NAME},
            timeout=10
        )
        response.raise_for_status()
        return response.json()

    except Exception as e:
        log(f"No se pudo consultar estado deseado en backend: {e}")
        return None


def get_hls_health(hls_url: str) -> tuple[bool, str]:
    if not hls_url:
        return False, "el backend no proporciono una URL HLS"

    try:
        response = requests.get(hls_url, timeout=HLS_HEALTH_TIMEOUT)

        if response.status_code != 200:
            return False, f"HLS respondio HTTP {response.status_code}"

        if not response.text.lstrip().startswith("#EXTM3U"):
            return False, "la respuesta HLS no contiene un manifiesto valido"

        return True, ""
    except requests.RequestException as e:
        return False, str(e)


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
    log(f"Reinicio automatico tras {HLS_FAILURE_LIMIT} fallos HLS consecutivos")

    hls_failures = 0

    while True:
        control_state = get_control_state()
        running = is_stream_running()

        if control_state is None:
            report_status(running, "Backend no disponible, se mantiene el estado actual")
            time.sleep(POLL_INTERVAL)
            continue

        desired = bool(control_state.get("stream_enabled", False))
        hls_url = str(control_state.get("hls_url", "")).strip()

        if desired and not running:
            log("Backend solicita ACTIVAR streaming.")
            ok = run_systemctl("start")
            running = is_stream_running()
            report_status(running, "Streaming activado" if ok else "Error activando streaming")
            hls_failures = 0

        elif not desired and running:
            log("Backend solicita DETENER streaming.")
            ok = run_systemctl("stop")
            running = is_stream_running()
            report_status(running, "Streaming detenido" if ok else "Error deteniendo streaming")
            hls_failures = 0

        elif desired and running:
            hls_available, health_detail = get_hls_health(hls_url)

            if hls_available:
                if hls_failures:
                    log("El manifiesto HLS vuelve a estar disponible.")
                hls_failures = 0
                report_status(True, "Estado sincronizado")
            else:
                hls_failures += 1
                log(
                    f"HLS no disponible ({hls_failures}/{HLS_FAILURE_LIMIT}): "
                    f"{health_detail}"
                )

                if hls_failures >= HLS_FAILURE_LIMIT:
                    log("El servicio figura activo pero no publica HLS. Reiniciando streaming.")
                    ok = run_systemctl("restart")
                    running = is_stream_running()
                    detail = (
                        "Streaming reiniciado tras perder la publicacion HLS"
                        if ok and running
                        else "Error reiniciando streaming sin HLS"
                    )
                    report_status(running, detail)
                    hls_failures = 0
                else:
                    report_status(
                        True,
                        f"Servicio activo; esperando HLS ({hls_failures}/{HLS_FAILURE_LIMIT})"
                    )

        else:
            hls_failures = 0
            report_status(running, "Estado sincronizado")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
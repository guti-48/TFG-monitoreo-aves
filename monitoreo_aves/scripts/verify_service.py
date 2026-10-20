import argparse
import json
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener


def wait_for_backend(url, seconds, *, opener=None, clock=time.monotonic, sleep=time.sleep):
    opener = opener or build_opener(ProxyHandler({}))
    deadline = clock() + seconds
    last_error = 'Sin respuesta'
    while True:
        try:
            with opener.open(url, timeout=5) as response:
                health = json.load(response)
            required = {'status': 'ok', 'network_configured': True,
                        'security': 'required', 'security_configured': True,
                        'stream_security': 'required', 'stream_security_configured': True}
            invalid = [key for key, value in required.items() if health.get(key) != value]
            if invalid:
                raise ValueError('Configuracion incompleta: ' + ', '.join(invalid))
            return health
        except (OSError, URLError, ValueError) as exc:
            last_error = str(exc)
        if clock() >= deadline:
            raise RuntimeError(f'{url}: {last_error}')
        sleep(min(2, max(0, deadline - clock())))


def main():
    parser = argparse.ArgumentParser(description='Comprueba el backend local sin proxy ni resolucion de localhost.')
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--wait', type=int, default=120)
    args = parser.parse_args()
    config = {}
    for raw in (args.project / 'backend/birdmonitor.env').read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip().removeprefix('export ')
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            config[key.strip()] = value.strip().strip('"').strip("'")
    port = int(config.get('BIRDMONITOR_BACKEND_PORT', '8000'))
    url = f'http://127.0.0.1:{port}/health'
    try:
        wait_for_backend(url, max(1, min(args.wait, 300)))
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    print(f'Backend, red y credenciales verificados: {url}')


if __name__ == '__main__':
    main()

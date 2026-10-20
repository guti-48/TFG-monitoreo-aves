from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import time

import requests

from .node_config import CURRENT_DIR, NODE_API_TOKEN, NODE_NAME, OUTPUT_FOLDER_AUDIO, SERVER_URL
from .node_delivery import Target, enabled, load_targets


REPORT_INTERVAL = 300
_last_report = None


def recordings_usage(root, *, scan_seconds=2, clock=time.monotonic):
    deadline = clock() + scan_seconds
    pending = [Path(root)]
    size = count = 0
    try:
        while pending:
            with os.scandir(pending.pop()) as entries:
                for entry in entries:
                    if clock() >= deadline:
                        return None, None
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.name.lower().endswith('.wav') and entry.is_file(follow_symlinks=False):
                            size += entry.stat(follow_symlinks=False).st_size
                            count += 1
                    except FileNotFoundError:
                        continue
    except OSError:
        return None, None
    return size, count


def collect_storage(root=CURRENT_DIR, recordings=OUTPUT_FOLDER_AUDIO):
    disk = shutil.disk_usage(root)
    size, count = recordings_usage(recordings)
    return {
        "device_name": NODE_NAME,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "total_bytes": disk.total, "free_bytes": disk.free,
        "recordings_bytes": size, "recordings_count": count,
    }


def report_storage(*, clock=time.monotonic):
    global _last_report
    now = clock()
    if _last_report is not None and now - _last_report < REPORT_INTERVAL:
        return
    _last_report = now
    try:
        payload = collect_storage()
        targets = (load_targets(os.environ['BIRDMONITOR_INGEST_TARGETS_FILE']) if enabled()
                   else [Target('principal', SERVER_URL, NODE_API_TOKEN)])
        with requests.Session() as session:
            session.trust_env = False
            for target in targets:
                try:
                    response = session.post(
                        target.url + '/node/storage', json=payload,
                        headers={'Authorization': f'Bearer {target.token}'},
                        timeout=(3, 3), allow_redirects=False,
                    )
                    if response.status_code != 200:
                        print(f'Almacenamiento pendiente para {target.name}: HTTP {response.status_code}')
                except requests.RequestException:
                    print(f'Almacenamiento pendiente para {target.name}: servidor no disponible')
    except (OSError, ValueError, KeyError):
        print('No se pudo medir o enviar el almacenamiento; se reintentara en el proximo ciclo')

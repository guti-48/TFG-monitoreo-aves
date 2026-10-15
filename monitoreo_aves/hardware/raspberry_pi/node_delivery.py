import ipaddress
import json
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
import time
from urllib.parse import urlsplit

import requests

from node_config import CURRENT_DIR, OUTPUT_FOLDER_AUDIO, OUTPUT_FOLDER_IMG, SERVER_URL


CONTEXT_KEY = "_deployment_context"
PRIVATE_NETWORKS = tuple(ipaddress.ip_network(value) for value in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "100.64.0.0/10", "127.0.0.0/8",
))


@dataclass(frozen=True)
class Target:
    name: str
    url: str
    token: str = field(repr=False)


def enabled():
    return bool(os.getenv("BIRDMONITOR_INGEST_TARGETS_FILE", "").strip())


def load_targets(path):
    try:
        path = Path(path)
        if not path.is_absolute():
            path = Path(CURRENT_DIR) / path
        if path.stat().st_size > 65536:
            raise ValueError
        values = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(values, list) or not 1 <= len(values) <= 8:
            raise ValueError
        targets = []
        for value in values:
            name, url, token = value["name"], value["url"], value["token"]
            if not isinstance(name, str) or not name or len(name) > 64:
                raise ValueError
            if not isinstance(token, str) or len(token) < 32 or any(c.isspace() for c in token):
                raise ValueError
            parsed = urlsplit(url)
            address = ipaddress.IPv4Address(parsed.hostname)
            if (parsed.scheme not in ("http", "https")
                    or parsed.username or parsed.password or parsed.query or parsed.fragment
                    or parsed.path not in ("", "/")
                    or not any(address in network for network in PRIVATE_NETWORKS)):
                raise ValueError
            if parsed.port is not None and not 1 <= parsed.port <= 65535:
                raise ValueError
            target = Target(name, url.rstrip("/"), token)
            if any(t.name == target.name or t.url == target.url for t in targets):
                raise ValueError
            targets.append(target)
        return targets
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise ValueError("Configuracion de destinos invalida; revisa IP privadas, nombres y tokens") from None


@lru_cache(maxsize=1)
def get_delivery():
    return Delivery(load_targets(os.environ["BIRDMONITOR_INGEST_TARGETS_FILE"]))


class Delivery:
    def __init__(self, targets, *, session=None, audio_dir=OUTPUT_FOLDER_AUDIO,
                 image_dir=OUTPUT_FOLDER_IMG, clock=time.monotonic):
        self.targets = targets
        self.session = session or requests.Session()
        self.session.trust_env = False
        self.audio_dir = Path(audio_dir)
        self.image_dir = Path(image_dir)
        self.clock = clock
        self.retry_at = {}
        self.preferred = None
        self.last_error = "Ningun destino disponible"

    def post(self, target, path, **kwargs):
        response = self.session.post(
            target.url + path,
            headers={"Authorization": f"Bearer {target.token}"},
            timeout=(60 if kwargs.get("files") else 3, 60), allow_redirects=False, **kwargs,
        )
        if response.status_code != 200:
            self.last_error = f"{target.name}: HTTP {response.status_code}"
            if response.status_code >= 500 or response.status_code in (401, 403, 429):
                self.retry_at[target.url] = self.clock() + 60
            return None
        return response

    def upload(self, target, payload):
        filename = payload["filename"]
        if not isinstance(filename, str) or Path(filename).name != filename or "\\" in filename:
            raise ValueError
        stem = filename[:-4] if filename.lower().endswith(".wav") else filename
        if not stem or stem in (".", ".."):
            raise ValueError
        audio = self.audio_dir / f"{stem}.wav"
        image = self.image_dir / f"{stem}.png"
        if not audio.is_file():
            self.last_error = "Falta el WAV local; el evento sigue pendiente"
            return False
        opened = []
        try:
            files = {}
            for key, path, mime in (("audio", audio, "audio/wav"), ("specto", image, "image/png")):
                if path.is_file():
                    handle = path.open("rb")
                    opened.append(handle)
                    files[key] = (path.name, handle, mime)
            fields = {key: payload[key] for key in ("device_name", "site_code", "deployment_public_id")}
            return self.post(target, "/upload/", data=fields, files=files) is not None
        finally:
            for handle in opened:
                handle.close()

    def deliver(self, event_type, payload):
        data = dict(payload)
        context = data.pop(CONTEXT_KEY, None)
        if event_type == "deployment_start":
            context = data
        if context and event_type != "deployment_start":
            if (context.get("device_name") != data.get("device_name")
                    or context.get("deployment_public_id") != data.get("deployment_public_id")
                    or context.get("site", {}).get("code") != data.get("site_code")):
                self.last_error = "El evento no coincide con su contexto; se conserva en cola"
                return False
        targets = sorted(self.targets, key=lambda target: target.url != self.preferred)
        for target in targets:
            if self.retry_at.get(target.url, 0) > self.clock():
                continue
            if event_type == "file_upload" and target.url != SERVER_URL:
                continue
            try:
                if context and self.post(target, "/node/deployments/register", json=context) is None:
                    continue
                if event_type == "deployment_start":
                    ok = context is not None
                elif event_type in ("detection", "audio_metric"):
                    data["filename"] = (data["filename"] if data["filename"].lower().endswith(".wav")
                                        else data["filename"] + ".wav")
                    endpoint = "/detections/" if event_type == "detection" else "/audio-metrics/"
                    response = self.post(target, endpoint, json=data)
                    ok = response is not None
                    if ok and event_type == "audio_metric" and data.get("acoustic_metrics_version") == "maad-v2":
                        ok = response.json().get("acoustic_metrics_version") == "maad-v2"
                        if not ok:
                            self.last_error = f"{target.name}: no confirma metricas maad-v2"
                    if ok and event_type == "detection":
                        ok = self.upload(target, data)
                elif event_type == "file_upload":
                    ok = self.upload(target, data)
                else:
                    self.last_error = "Tipo de evento desconocido; se conserva en cola"
                    return False
                if ok:
                    self.preferred = target.url
                    self.last_error = ""
                    return True
            except requests.exceptions.RequestException:
                self.retry_at[target.url] = self.clock() + 60
                self.last_error = f"{target.name}: conexion no disponible; se reintentara"
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                self.last_error = f"{target.name}: evento, archivo o respuesta no validos"
        return False

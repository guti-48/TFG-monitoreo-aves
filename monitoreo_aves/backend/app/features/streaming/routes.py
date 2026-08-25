import json
import os
import re
from datetime import datetime, timezone
from threading import Lock
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ...core.config import (
    CONFIGURED_STREAM_BASE_URL,
    CONFIGURED_STREAM_RTSP_BASE_URL,
    DEFAULT_STREAM_PATH,
    STREAM_CONTROL_FILE,
    STREAM_PATH_TEMPLATE,
)
from .security import get_stream_security_settings


router = APIRouter()
stream_lock = Lock()


def _read_status_stale_seconds() -> int:
    try:
        return max(
            15,
            int(os.getenv("BIRDMONITOR_STREAM_STATUS_STALE_SECONDS", "30")),
        )
    except (TypeError, ValueError):
        return 30


STREAM_STATUS_STALE_SECONDS = _read_status_stale_seconds()
_TRANSIENT_STREAM_FIELDS = {
    "hls_url",
    "page_url",
    "rtsp_url",
    "status_stale",
    "last_status_age_seconds",
    "reported_actual_running",
    "reported_hls_available",
    "playback_ready",
}


class StreamControlUpdate(BaseModel):
    node_name: str = "birdmonitor"
    stream_enabled: bool
    stream_path: str | None = None


class StreamStatusUpdate(BaseModel):
    node_name: str = "birdmonitor"
    running: bool
    hls_available: bool | None = None
    detail: str = ""
    stream_path: str | None = None


def _slugify_stream_part(value: str | None) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", (value or "").strip()).strip("-")
    return clean or "birdmonitor"


def _normalize_stream_path(value: str | None) -> str:
    clean = (value or "").strip().strip("/")
    clean = re.sub(r"[^A-Za-z0-9_./-]+", "-", clean)
    clean = re.sub(r"/+", "/", clean).strip("/")
    clean = "/".join(
        part for part in clean.split("/") if part not in {"", ".", ".."}
    )
    return clean or "birdmonitor-audio"


def _stream_path_for_node(node_name: str) -> str:
    node_slug = _slugify_stream_part(node_name)

    if DEFAULT_STREAM_PATH:
        if "{node_name}" in DEFAULT_STREAM_PATH or "{node_slug}" in DEFAULT_STREAM_PATH:
            try:
                return _normalize_stream_path(
                    DEFAULT_STREAM_PATH.format(
                        node_name=node_slug,
                        node_slug=node_slug,
                    )
                )
            except (KeyError, ValueError):
                return _normalize_stream_path(f"{node_slug}-audio")
        return _normalize_stream_path(DEFAULT_STREAM_PATH)

    template = STREAM_PATH_TEMPLATE or "{node_name}-audio"
    try:
        return _normalize_stream_path(
            template.format(node_name=node_slug, node_slug=node_slug)
        )
    except (KeyError, ValueError):
        return _normalize_stream_path(f"{node_slug}-audio")


def _stream_base_url(request: Request | None = None) -> str:
    stream_security = get_stream_security_settings()
    if stream_security.enabled:
        if request is None:
            return "http://127.0.0.1:8000/stream/hls"
        return f"{str(request.base_url).rstrip('/')}/stream/hls"

    if CONFIGURED_STREAM_BASE_URL:
        return CONFIGURED_STREAM_BASE_URL.rstrip("/")

    if request is None:
        return "http://127.0.0.1:8888"

    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return f"{scheme}://{host}:8888"


def _stream_rtsp_base_url(request: Request | None = None) -> str:
    if CONFIGURED_STREAM_RTSP_BASE_URL:
        base_url = CONFIGURED_STREAM_RTSP_BASE_URL.rstrip("/")
    else:
        host = request.url.hostname if request is not None else "127.0.0.1"
        base_url = f"rtsp://{host or '127.0.0.1'}:8554"

    stream_security = get_stream_security_settings()
    role = getattr(
        getattr(request, "state", None),
        "security_role",
        "",
    )
    if (
        stream_security.enabled
        and stream_security.configured
        and role == "admin"
    ):
        parsed = urlsplit(base_url)
        host = parsed.hostname or "127.0.0.1"
        netloc = f"[{host}]" if ":" in host else host
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        user = quote(stream_security.reader_user, safe="")
        password = quote(stream_security.reader_password, safe="")
        return urlunsplit(
            (
                parsed.scheme or "rtsp",
                f"{user}:{password}@{netloc}",
                parsed.path.rstrip("/"),
                "",
                "",
            )
        ).rstrip("/")

    return base_url


def _status_freshness(last_status_at: object) -> tuple[bool, float | None]:
    if not last_status_at:
        return True, None

    try:
        parsed = datetime.fromisoformat(str(last_status_at).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        age_seconds = max(
            0.0,
            (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds(),
        )
    except (TypeError, ValueError):
        return True, None

    return age_seconds > STREAM_STATUS_STALE_SECONDS, round(age_seconds, 1)


def _legacy_hls_available(payload: StreamStatusUpdate) -> bool:
    """Interpreta reportes de supervisores anteriores al campo hls_available."""
    if not payload.running:
        return False

    detail = payload.detail.strip().casefold()
    return detail in {"estado sincronizado", "hls disponible"}


def _apply_stream_urls(current: dict, request: Request | None = None) -> dict:
    current = dict(current)
    base_url = _stream_base_url(request)
    rtsp_base_url = _stream_rtsp_base_url(request)
    node_name = current.get("node_name", "birdmonitor")
    stream_path = _normalize_stream_path(
        current.get("stream_path") or _stream_path_for_node(node_name)
    )

    current["stream_path"] = stream_path
    current["hls_url"] = f"{base_url}/{stream_path}/index.m3u8"
    current["page_url"] = f"{base_url}/{stream_path}/"
    current["rtsp_url"] = f"{rtsp_base_url}/{stream_path}"

    status_stale, status_age = _status_freshness(current.get("last_status_at"))
    reported_running = bool(current.get("actual_running", False))
    reported_hls_available = bool(current.get("hls_available", False))

    current["reported_actual_running"] = reported_running
    current["reported_hls_available"] = reported_hls_available
    current["status_stale"] = status_stale
    current["last_status_age_seconds"] = status_age
    current["actual_running"] = reported_running and not status_stale
    current["hls_available"] = reported_hls_available and not status_stale
    current["playback_ready"] = bool(
        current["actual_running"] and current["hls_available"]
    )

    if status_stale and current.get("stream_enabled"):
        current["detail"] = (
            "Nodo sin telemetria reciente; comprueba su alimentacion y conexion"
        )

    return current


def _stream_default_state(node_name: str) -> dict:
    return {
        "node_name": node_name,
        "stream_path": _stream_path_for_node(node_name),
        "stream_enabled": False,
        "actual_running": False,
        "hls_available": False,
        "detail": "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_status_at": None,
    }


def _load_stream_state() -> dict:
    if not STREAM_CONTROL_FILE.exists():
        return {}

    try:
        with open(STREAM_CONTROL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stream_state(state: dict) -> None:
    state_to_store = {
        node_name: {
            key: value
            for key, value in current.items()
            if key not in _TRANSIENT_STREAM_FIELDS
        }
        for node_name, current in state.items()
    }
    with open(STREAM_CONTROL_FILE, "w", encoding="utf-8") as f:
        json.dump(state_to_store, f, ensure_ascii=False, indent=2)


@router.get("/stream/control")
def get_stream_control(request: Request, node_name: str = "birdmonitor"):
    """
    Devuelve el estado deseado y real conocido del streaming para un nodo.
    """
    with stream_lock:
        state = _load_stream_state()

        if node_name not in state:
            state[node_name] = _stream_default_state(node_name)
            _save_stream_state(state)

        return _apply_stream_urls(state[node_name], request)


@router.post("/stream/control")
def set_stream_control(payload: StreamControlUpdate, request: Request):
    """
    Cambia el estado deseado del streaming.
    El dashboard llama a este endpoint.
    La Raspberry lo consulta mediante streamSupervisor.py.
    """
    with stream_lock:
        state = _load_stream_state()

        current = state.get(payload.node_name, _stream_default_state(payload.node_name))
        current["stream_enabled"] = payload.stream_enabled
        if payload.stream_path:
            current["stream_path"] = _normalize_stream_path(payload.stream_path)
        current["updated_at"] = datetime.now(timezone.utc).isoformat()
        state[payload.node_name] = current
        _save_stream_state(state)

        return _apply_stream_urls(current, request)


@router.post("/stream/status")
def set_stream_status(payload: StreamStatusUpdate):
    """
    La Raspberry informa del estado real de birdstream.service.
    """
    with stream_lock:
        state = _load_stream_state()

        current = state.get(payload.node_name, _stream_default_state(payload.node_name))
        current["actual_running"] = payload.running
        if payload.hls_available is not None:
            current["hls_available"] = payload.hls_available
        else:
            current["hls_available"] = _legacy_hls_available(payload)
        current["detail"] = payload.detail
        if payload.stream_path:
            current["stream_path"] = _normalize_stream_path(payload.stream_path)
        current["last_status_at"] = datetime.now(timezone.utc).isoformat()

        state[payload.node_name] = current
        _save_stream_state(state)

        return _apply_stream_urls(current)
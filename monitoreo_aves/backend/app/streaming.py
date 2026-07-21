import json
import re
from datetime import datetime, timezone
from threading import Lock

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .config import (
    CONFIGURED_STREAM_BASE_URL,
    DEFAULT_STREAM_PATH,
    STREAM_CONTROL_FILE,
    STREAM_PATH_TEMPLATE,
)


router = APIRouter()
stream_lock = Lock()


class StreamControlUpdate(BaseModel):
    node_name: str = "birdmonitor"
    stream_enabled: bool
    stream_path: str | None = None


class StreamStatusUpdate(BaseModel):
    node_name: str = "birdmonitor"
    running: bool
    detail: str = ""
    stream_path: str | None = None


def _slugify_stream_part(value: str | None) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "-", (value or "").strip()).strip("-")
    return clean or "birdmonitor"


def _normalize_stream_path(value: str | None) -> str:
    clean = (value or "").strip().strip("/")
    clean = re.sub(r"[^A-Za-z0-9_./-]+", "-", clean)
    clean = re.sub(r"/+", "/", clean).strip("/")
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
    if CONFIGURED_STREAM_BASE_URL:
        return CONFIGURED_STREAM_BASE_URL.rstrip("/")

    if request is None:
        return "http://127.0.0.1:8888"

    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return f"{scheme}://{host}:8888"


def _apply_stream_urls(current: dict, request: Request | None = None) -> dict:
    base_url = _stream_base_url(request)
    node_name = current.get("node_name", "birdmonitor")
    stream_path = _normalize_stream_path(
        current.get("stream_path") or _stream_path_for_node(node_name)
    )

    current["stream_path"] = stream_path
    current["hls_url"] = f"{base_url}/{stream_path}/index.m3u8"
    current["page_url"] = f"{base_url}/{stream_path}/"
    return current


def _stream_default_state(node_name: str) -> dict:
    return _apply_stream_urls({
        "node_name": node_name,
        "stream_path": _stream_path_for_node(node_name),
        "stream_enabled": False,
        "actual_running": False,
        "detail": "",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "last_status_at": None,
    })


def _load_stream_state() -> dict:
    if not STREAM_CONTROL_FILE.exists():
        return {}

    try:
        with open(STREAM_CONTROL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_stream_state(state: dict) -> None:
    with open(STREAM_CONTROL_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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

        state[node_name] = _apply_stream_urls(state[node_name], request)

        return state[node_name]


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
        current = _apply_stream_urls(current, request)

        state[payload.node_name] = current
        _save_stream_state(state)

        return current


@router.post("/stream/status")
def set_stream_status(payload: StreamStatusUpdate):
    """
    La Raspberry informa del estado real de birdstream.service.
    """
    with stream_lock:
        state = _load_stream_state()

        current = state.get(payload.node_name, _stream_default_state(payload.node_name))
        current["actual_running"] = payload.running
        current["detail"] = payload.detail
        if payload.stream_path:
            current["stream_path"] = _normalize_stream_path(payload.stream_path)
        current["last_status_at"] = datetime.now(timezone.utc).isoformat()

        state[payload.node_name] = current
        _save_stream_state(state)

        return current

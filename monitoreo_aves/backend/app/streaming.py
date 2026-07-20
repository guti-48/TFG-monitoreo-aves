import json
from datetime import datetime, timezone
from threading import Lock

from fastapi import APIRouter, Request
from pydantic import BaseModel

from .config import (
    CONFIGURED_STREAM_BASE_URL,
    DEFAULT_STREAM_PATH,
    STREAM_CONTROL_FILE,
)


router = APIRouter()
stream_lock = Lock()


class StreamControlUpdate(BaseModel):
    node_name: str = "birdmonitor"
    stream_enabled: bool


class StreamStatusUpdate(BaseModel):
    node_name: str = "birdmonitor"
    running: bool
    detail: str = ""


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
    current["hls_url"] = f"{base_url}/{DEFAULT_STREAM_PATH}/index.m3u8"
    current["page_url"] = f"{base_url}/{DEFAULT_STREAM_PATH}/"
    return current


def _stream_default_state(node_name: str) -> dict:
    return _apply_stream_urls({
        "node_name": node_name,
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
        current["last_status_at"] = datetime.now(timezone.utc).isoformat()

        state[payload.node_name] = current
        _save_stream_state(state)

        return current

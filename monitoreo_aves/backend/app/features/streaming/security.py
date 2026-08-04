from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import logging
import os
import re
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
import httpx
from pydantic import BaseModel


router = APIRouter()
logger = logging.getLogger(__name__)

_LOOPBACK_ADDRESSES = {"127.0.0.1", "::1"}
_SAFE_HLS_RESOURCE = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
)
_SAFE_STREAM_PATH = re.compile(
    r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*"
)
_FORWARDED_RESPONSE_HEADERS = {
    "accept-ranges",
    "cache-control",
    "content-length",
    "content-range",
    "content-type",
    "etag",
    "last-modified",
}


@dataclass(frozen=True)
class StreamSecuritySettings:
    mode: str
    publish_user: str
    publish_password_hash: str
    reader_user: str
    reader_password: str
    proxy_user: str
    proxy_password: str
    hls_internal_url: str

    @property
    def enabled(self) -> bool:
        return self.mode == "required"

    @property
    def configured(self) -> bool:
        return not stream_security_configuration_errors(self)


class MediaMtxAuthPayload(BaseModel):
    user: str = ""
    password: str = ""
    token: str = ""
    ip: str = ""
    action: str = ""
    path: str = ""
    protocol: str = ""
    id: str = ""
    query: str = ""
    userAgent: str = ""


def get_stream_security_settings() -> StreamSecuritySettings:
    mode = os.getenv(
        "BIRDMONITOR_STREAM_SECURITY_MODE",
        "required",
    ).strip().lower()
    if mode not in {"required", "disabled"}:
        mode = "required"

    return StreamSecuritySettings(
        mode=mode,
        publish_user=os.getenv(
            "BIRDMONITOR_STREAM_PUBLISH_USER",
            "",
        ).strip(),
        publish_password_hash=os.getenv(
            "BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH",
            "",
        ).strip(),
        reader_user=os.getenv(
            "BIRDMONITOR_STREAM_READER_USER",
            "",
        ).strip(),
        reader_password=os.getenv(
            "BIRDMONITOR_STREAM_READER_PASSWORD",
            "",
        ).strip(),
        proxy_user=os.getenv(
            "BIRDMONITOR_STREAM_PROXY_USER",
            "",
        ).strip(),
        proxy_password=os.getenv(
            "BIRDMONITOR_STREAM_PROXY_PASSWORD",
            "",
        ).strip(),
        hls_internal_url=os.getenv(
            "BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL",
            "http://127.0.0.1:8888",
        ).strip().rstrip("/"),
    )


def stream_security_configuration_errors(
    settings: StreamSecuritySettings | None = None,
) -> list[str]:
    settings = settings or get_stream_security_settings()
    if not settings.enabled:
        return []

    errors = []
    if not settings.publish_user:
        errors.append("falta BIRDMONITOR_STREAM_PUBLISH_USER")
    if not settings.publish_password_hash.startswith("sha256$"):
        errors.append("falta BIRDMONITOR_STREAM_PUBLISH_PASSWORD_HASH")
    if not settings.reader_user:
        errors.append("falta BIRDMONITOR_STREAM_READER_USER")
    if len(settings.reader_password) < 24:
        errors.append("falta BIRDMONITOR_STREAM_READER_PASSWORD")
    if not settings.proxy_user:
        errors.append("falta BIRDMONITOR_STREAM_PROXY_USER")
    if len(settings.proxy_password) < 24:
        errors.append("falta BIRDMONITOR_STREAM_PROXY_PASSWORD")
    if not settings.hls_internal_url.startswith(("http://", "https://")):
        errors.append("BIRDMONITOR_MEDIAMTX_HLS_INTERNAL_URL no es valida")
    return errors


def hash_stream_password(password: str) -> str:
    return f"sha256${hashlib.sha256(password.encode('utf-8')).hexdigest()}"


def _password_matches(password: str, expected_hash: str) -> bool:
    if not password or not expected_hash.startswith("sha256$"):
        return False
    return hmac.compare_digest(
        hash_stream_password(password),
        expected_hash,
    )


def _secret_matches(candidate: str, expected: str) -> bool:
    if not candidate or not expected:
        return False
    return hmac.compare_digest(candidate, expected)


def _request_is_loopback(request: Request) -> bool:
    return bool(
        request.client
        and request.client.host in _LOOPBACK_ADDRESSES
    )


def _valid_stream_path(path: str) -> bool:
    return bool(
        path
        and _SAFE_STREAM_PATH.fullmatch(path)
        and all(part not in {".", ".."} for part in path.split("/"))
    )


def _valid_hls_resource(resource: str) -> bool:
    return bool(
        resource
        and _SAFE_HLS_RESOURCE.fullmatch(resource)
        and all(part not in {".", ".."} for part in resource.split("/"))
    )


def _credentials_from_payload(
    payload: MediaMtxAuthPayload,
) -> tuple[str, str]:
    if payload.user or payload.password:
        return payload.user, payload.password

    token_user, separator, token_password = payload.token.partition(":")
    if separator:
        return token_user, token_password
    return "", ""


@router.post(
    "/internal/mediamtx/auth",
    include_in_schema=False,
)
def authorize_mediamtx(
    payload: MediaMtxAuthPayload,
    request: Request,
):
    if not _request_is_loopback(request):
        raise HTTPException(status_code=403, detail="Acceso interno requerido")

    settings = get_stream_security_settings()
    if not settings.enabled or not settings.configured:
        raise HTTPException(
            status_code=503,
            detail="Seguridad de streaming no configurada",
        )

    if not _valid_stream_path(payload.path):
        raise HTTPException(status_code=401, detail="Ruta no autorizada")

    user, password = _credentials_from_payload(payload)
    action = payload.action.strip().lower()
    protocol = payload.protocol.strip().lower()

    publisher_allowed = (
        action == "publish"
        and protocol == "rtsp"
        and hmac.compare_digest(user, settings.publish_user)
        and _password_matches(
            password,
            settings.publish_password_hash,
        )
    )
    reader_allowed = (
        action == "read"
        and protocol == "rtsp"
        and hmac.compare_digest(user, settings.reader_user)
        and _secret_matches(password, settings.reader_password)
    )
    proxy_allowed = (
        action == "read"
        and protocol == "hls"
        and hmac.compare_digest(user, settings.proxy_user)
        and _secret_matches(password, settings.proxy_password)
    )

    if publisher_allowed or reader_allowed or proxy_allowed:
        return Response(status_code=204)

    # No se registra nunca la credencial recibida. Estos indicadores permiten
    # distinguir un usuario incorrecto de una contraseña incorrecta al
    # diagnosticar FFmpeg/MediaMTX sin exponer secretos en los logs.
    logger.warning(
        "MediaMTX auth rechazada: action=%s protocol=%s path_valida=%s "
        "usuario_presente=%s clave_presente=%s usuario_publicador_ok=%s "
        "clave_publicador_ok=%s usuario_lector_ok=%s clave_lector_ok=%s "
        "usuario_proxy_ok=%s clave_proxy_ok=%s",
        action or "-",
        protocol or "-",
        _valid_stream_path(payload.path),
        bool(user),
        bool(password),
        bool(user and hmac.compare_digest(user, settings.publish_user)),
        _password_matches(password, settings.publish_password_hash),
        bool(user and hmac.compare_digest(user, settings.reader_user)),
        _secret_matches(password, settings.reader_password),
        bool(user and hmac.compare_digest(user, settings.proxy_user)),
        _secret_matches(password, settings.proxy_password),
    )
    raise HTTPException(status_code=401, detail="Credenciales no validas")


def _upstream_hls_url(
    settings: StreamSecuritySettings,
    resource: str,
) -> str:
    safe_parts = [quote(part, safe="._-") for part in resource.split("/")]
    return f"{settings.hls_internal_url}/{'/'.join(safe_parts)}"


def _validated_hls_query(request: Request) -> dict[str, str]:
    sessions = request.query_params.getlist("session")
    if not sessions:
        return {}
    if len(sessions) != 1:
        raise HTTPException(
            status_code=400,
            detail="Sesion HLS no valida",
        )

    session = sessions[0]
    try:
        parsed_session = UUID(session)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="Sesion HLS no valida",
        ) from exc
    if str(parsed_session) != session.lower():
        raise HTTPException(
            status_code=400,
            detail="Sesion HLS no valida",
        )
    return {"session": session}


@router.get(
    "/stream/hls/{resource:path}",
    include_in_schema=False,
)
async def proxy_hls(resource: str, request: Request):
    settings = get_stream_security_settings()
    if not settings.enabled or not settings.configured:
        raise HTTPException(
            status_code=503,
            detail="Seguridad de streaming no configurada",
        )
    if not _valid_hls_resource(resource):
        raise HTTPException(status_code=400, detail="Ruta HLS no valida")

    upstream_headers = {}
    for header_name in ("accept", "if-none-match", "range"):
        header_value = request.headers.get(header_name)
        if header_value:
            upstream_headers[header_name] = header_value

    client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=3.0,
            read=20.0,
            write=5.0,
            pool=5.0,
        ),
        # MediaMTX comprueba la compatibilidad de cookies de HLS con una
        # redireccion interna que añade ``?cookieCheck=1``. Debe resolverla
        # el backend para no exponer ni la URL interna ni sus credenciales.
        follow_redirects=True,
        max_redirects=3,
    )
    try:
        upstream_request = client.build_request(
            "GET",
            _upstream_hls_url(settings, resource),
            headers=upstream_headers,
            params=_validated_hls_query(request),
        )
        upstream_response = await client.send(
            upstream_request,
            auth=httpx.BasicAuth(
                settings.proxy_user,
                settings.proxy_password,
            ),
            stream=True,
        )
    except httpx.HTTPError as exc:
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="MediaMTX no esta disponible",
        ) from exc

    if upstream_response.status_code in {401, 403}:
        await upstream_response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=502,
            detail="MediaMTX rechazo al proxy interno",
        )

    response_headers = {
        name: value
        for name, value in upstream_response.headers.items()
        if name.lower() in _FORWARDED_RESPONSE_HEADERS
    }
    if resource.lower().endswith(".m3u8"):
        response_headers["cache-control"] = "no-store"

    async def stream_body():
        try:
            async for chunk in upstream_response.aiter_raw():
                yield chunk
        finally:
            await upstream_response.aclose()
            await client.aclose()

    if upstream_response.status_code == 304:
        await upstream_response.aclose()
        await client.aclose()
        return Response(
            status_code=304,
            headers=response_headers,
        )

    return StreamingResponse(
        stream_body(),
        status_code=upstream_response.status_code,
        headers=response_headers,
    )

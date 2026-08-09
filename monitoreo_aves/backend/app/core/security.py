from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
import hashlib
import hmac
import json
import os
import secrets
import time

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse


SESSION_COOKIE_NAME = "birdmonitor_session"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_PATHS = {
    "/health",
    "/login",
    "/auth/login",
    "/internal/mediamtx/auth",
}
NODE_PERMISSIONS = {
    ("POST", "/devices/"),
    ("POST", "/detections/"),
    ("POST", "/audio-metrics/"),
    ("POST", "/upload/"),
    ("POST", "/node/deployments/activate"),
    ("GET", "/stream/control"),
    ("POST", "/stream/status"),
}


@dataclass(frozen=True)
class SecuritySettings:
    mode: str
    admin_username: str
    admin_password_hash: str
    node_token_hash: str
    session_secret: str
    session_hours: int
    cookie_secure: bool

    @property
    def enabled(self) -> bool:
        return self.mode == "required"

    @property
    def configured(self) -> bool:
        return not security_configuration_errors(self)


def get_security_settings() -> SecuritySettings:
    mode = os.getenv("BIRDMONITOR_SECURITY_MODE", "required").strip().lower()
    if mode not in {"required", "disabled"}:
        mode = "required"

    try:
        session_hours = max(
            1,
            min(168, int(os.getenv("BIRDMONITOR_SESSION_HOURS", "12"))),
        )
    except ValueError:
        session_hours = 12

    return SecuritySettings(
        mode=mode,
        admin_username=os.getenv(
            "BIRDMONITOR_ADMIN_USERNAME",
            "admin",
        ).strip(),
        admin_password_hash=os.getenv(
            "BIRDMONITOR_ADMIN_PASSWORD_HASH",
            "",
        ).strip(),
        node_token_hash=os.getenv(
            "BIRDMONITOR_NODE_TOKEN_HASH",
            "",
        ).strip(),
        session_secret=os.getenv(
            "BIRDMONITOR_SESSION_SECRET",
            "",
        ).strip(),
        session_hours=session_hours,
        cookie_secure=os.getenv(
            "BIRDMONITOR_COOKIE_SECURE",
            "0",
        ).strip() == "1",
    )


def security_configuration_errors(
    settings: SecuritySettings | None = None,
) -> list[str]:
    settings = settings or get_security_settings()
    errors = []

    if not settings.admin_username:
        errors.append("falta BIRDMONITOR_ADMIN_USERNAME")
    if not settings.admin_password_hash.startswith("scrypt$"):
        errors.append("falta BIRDMONITOR_ADMIN_PASSWORD_HASH")
    if not settings.node_token_hash.startswith("sha256$"):
        errors.append("falta BIRDMONITOR_NODE_TOKEN_HASH")
    if len(settings.session_secret) < 32:
        errors.append("falta BIRDMONITOR_SESSION_SECRET")

    return errors


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}")


def hash_admin_password(password: str, salt: bytes | None = None) -> str:
    if len(password) < 12:
        raise ValueError("La contrasena debe tener al menos 12 caracteres")

    salt = salt or secrets.token_bytes(16)
    n, r, p = 2**14, 8, 1
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=32,
    )
    return f"scrypt${n}${r}${p}${_b64encode(salt)}${_b64encode(digest)}"


def verify_admin_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = stored_hash.split("$", 5)
        if algorithm != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_b64decode(salt),
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=32,
        )
        return hmac.compare_digest(digest, _b64decode(expected))
    except (TypeError, ValueError, binascii.Error):
        return False


def hash_node_token(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"sha256${digest}"


def verify_node_token(token: str, stored_hash: str) -> bool:
    if not token or not stored_hash.startswith("sha256$"):
        return False
    return hmac.compare_digest(hash_node_token(token), stored_hash)


def create_session_token(
    username: str,
    settings: SecuritySettings,
) -> str:
    payload = {
        "sub": username,
        "exp": int(time.time()) + settings.session_hours * 3600,
        "nonce": secrets.token_urlsafe(12),
    }
    encoded_payload = _b64encode(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    )
    signature = hmac.new(
        settings.session_secret.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_b64encode(signature)}"


def verify_session_token(
    token: str,
    settings: SecuritySettings,
) -> str | None:
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = hmac.new(
            settings.session_secret.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(
            expected_signature,
            _b64decode(encoded_signature),
        ):
            return None

        payload = json.loads(_b64decode(encoded_payload))
        if int(payload.get("exp", 0)) < int(time.time()):
            return None

        username = str(payload.get("sub", ""))
        if not hmac.compare_digest(username, settings.admin_username):
            return None
        return username
    except (TypeError, ValueError, binascii.Error, json.JSONDecodeError):
        return None


def _extract_bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, _, token = authorization.partition(" ")
    if scheme.casefold() != "bearer":
        return ""
    return token.strip()


def _node_request_allowed(request: Request) -> bool:
    method = request.method.upper()
    path = request.url.path
    return (
        (method, path) in NODE_PERMISSIONS
        or (method == "GET" and path.startswith("/stream/hls/"))
    )


def _is_html_navigation(request: Request) -> bool:
    return (
        request.method == "GET"
        and "text/html" in request.headers.get("accept", "")
    )


def _csrf_is_valid(request: Request) -> bool:
    return request.headers.get("x-birdmonitor-csrf") == "1"


async def security_middleware(request: Request, call_next):
    settings = get_security_settings()
    path = request.url.path

    if not settings.enabled:
        request.state.security_role = "disabled"
        response = await call_next(request)
        return _add_security_headers(response)

    if path in PUBLIC_PATHS or request.method == "OPTIONS":
        response = await call_next(request)
        return _add_security_headers(response)

    if not settings.configured:
        return _add_security_headers(
            JSONResponse(
                status_code=503,
                content={
                    "detail": (
                        "La seguridad de BirdMonitor aun no esta configurada. "
                        "Ejecuta scripts/configure_security.py en el servidor."
                    )
                },
            )
        )

    node_token = _extract_bearer_token(request)
    if verify_node_token(node_token, settings.node_token_hash):
        if not _node_request_allowed(request):
            return _add_security_headers(
                JSONResponse(
                    status_code=403,
                    content={
                        "detail": "El token del nodo no permite esta operacion"
                    },
                )
            )
        request.state.security_role = "node"
        response = await call_next(request)
        return _add_security_headers(response)

    session_token = request.cookies.get(SESSION_COOKIE_NAME, "")
    username = verify_session_token(session_token, settings)
    if username:
        if (
            request.method not in SAFE_METHODS
            and path != "/auth/logout"
            and not _csrf_is_valid(request)
        ):
            return _add_security_headers(
                JSONResponse(
                    status_code=403,
                    content={"detail": "Falta la proteccion CSRF"},
                )
            )
        request.state.security_role = "admin"
        request.state.security_username = username
        response = await call_next(request)
        return _add_security_headers(response)

    if _is_html_navigation(request):
        return _add_security_headers(
            RedirectResponse(url="/login", status_code=303)
        )

    return _add_security_headers(
        JSONResponse(
            status_code=401,
            content={"detail": "Autenticacion requerida"},
        )
    )


def _add_security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response
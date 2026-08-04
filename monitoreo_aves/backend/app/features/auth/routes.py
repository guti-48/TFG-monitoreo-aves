from __future__ import annotations

from collections import defaultdict, deque
from html import escape
import hmac
import threading
import time

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from ...core.security import (
    SESSION_COOKIE_NAME,
    create_session_token,
    get_security_settings,
    security_configuration_errors,
    verify_admin_password,
)


router = APIRouter(tags=["authentication"])
_ATTEMPT_WINDOW_SECONDS = 300
_MAX_ATTEMPTS = 8
_attempts: dict[str, deque[float]] = defaultdict(deque)
_attempts_lock = threading.Lock()


def _login_page(message: str = "", status_code: int = 200) -> HTMLResponse:
    settings = get_security_settings()
    errors = security_configuration_errors(settings) if settings.enabled else []
    setup_message = ""

    if errors:
        setup_message = (
            "<div class='notice'>La protección todavía no está configurada. "
            "Ejecuta <code>python scripts/configure_security.py</code> "
            "en el servidor antes de iniciar sesión.</div>"
        )

    error_message = (
        f"<div class='error'>{escape(message)}</div>"
        if message
        else ""
    )
    username = escape(settings.admin_username or "admin")

    return HTMLResponse(
        status_code=status_code,
        content=f"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Acceso · BirdMonitor</title>
  <style>
    :root {{ color-scheme: light; font-family: system-ui, sans-serif; }}
    body {{
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      background: #f4f6f1; color: #243129;
    }}
    main {{
      width: min(390px, calc(100% - 36px)); padding: 32px;
      border: 1px solid #ced8d0; border-radius: 18px;
      background: #fff; box-shadow: 0 16px 40px rgba(31, 51, 40, .12);
    }}
    h1 {{ margin: 0 0 8px; color: #2f6f4e; }}
    p {{ color: #65736a; line-height: 1.5; }}
    label {{ display: block; margin: 18px 0 6px; font-weight: 700; }}
    input {{
      box-sizing: border-box; width: 100%; padding: 12px 14px;
      border: 1px solid #b9c7bd; border-radius: 9px; font: inherit;
    }}
    button {{
      width: 100%; margin-top: 22px; padding: 12px 14px;
      border: 0; border-radius: 9px; background: #2f6f4e;
      color: white; font: inherit; font-weight: 700; cursor: pointer;
    }}
    .error, .notice {{
      margin-top: 18px; padding: 12px; border-radius: 9px; line-height: 1.45;
    }}
    .error {{ background: #f7deda; color: #7b2f27; }}
    .notice {{ background: #f5ecd7; color: #6b5018; }}
    code {{ font-size: .85em; }}
  </style>
</head>
<body>
  <main>
    <h1>BirdMonitor</h1>
    <p>Acceso privado al panel de monitorización acústica.</p>
    {setup_message}
    {error_message}
    <form method="post" action="/auth/login">
      <label for="username">Usuario</label>
      <input id="username" name="username" value="{username}"
             autocomplete="username" required maxlength="64">
      <label for="password">Contraseña</label>
      <input id="password" name="password" type="password"
             autocomplete="current-password" required maxlength="256">
      <button type="submit">Entrar al panel</button>
    </form>
  </main>
</body>
</html>""",
    )


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _too_many_attempts(client_key: str) -> bool:
    now = time.monotonic()
    with _attempts_lock:
        attempts = _attempts[client_key]
        while attempts and now - attempts[0] > _ATTEMPT_WINDOW_SECONDS:
            attempts.popleft()
        return len(attempts) >= _MAX_ATTEMPTS


def _register_failure(client_key: str) -> None:
    with _attempts_lock:
        _attempts[client_key].append(time.monotonic())


def _clear_failures(client_key: str) -> None:
    with _attempts_lock:
        _attempts.pop(client_key, None)


@router.get("/login", include_in_schema=False)
def login_page():
    return _login_page()


@router.post("/auth/login", include_in_schema=False)
def login(
    request: Request,
    username: str = Form(..., max_length=64),
    password: str = Form(..., max_length=256),
):
    settings = get_security_settings()
    client_key = _client_key(request)

    if not settings.enabled:
        return RedirectResponse(url="/", status_code=303)

    if not settings.configured:
        return _login_page("La seguridad todavía no está configurada.", 503)

    if _too_many_attempts(client_key):
        return _login_page(
            "Demasiados intentos. Espera unos minutos antes de repetir.",
            429,
        )

    valid_username = secrets_compare(username, settings.admin_username)
    valid_password = verify_admin_password(
        password,
        settings.admin_password_hash,
    )
    if not (valid_username and valid_password):
        _register_failure(client_key)
        return _login_page("Usuario o contraseña incorrectos.", 401)

    _clear_failures(client_key)
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session_token(settings.admin_username, settings),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="strict",
        path="/",
    )
    return response


def secrets_compare(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


@router.post("/auth/logout", include_in_schema=False)
def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )
    return response


@router.get("/auth/session", include_in_schema=False)
def session_status(request: Request):
    return JSONResponse(
        {
            "authenticated": True,
            "username": getattr(request.state, "security_username", "admin"),
        }
    )
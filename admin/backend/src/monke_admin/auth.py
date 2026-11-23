"""Google sign-in with an email allow-list, and HMAC-signed cookies (follows Engagement Bot Checker's pattern).

The ID token comes straight from Google's token endpoint over TLS, authenticated with the client secret, so its
signature is not re-verified (Google's documented allowance for this flow); its claims still are.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse

from monke_admin.settings import Settings

log = logging.getLogger(__name__)

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ("accounts.google.com", "https://accounts.google.com")
SESSION_COOKIE = "monke_admin_session"
STATE_COOKIE = "monke_admin_state"
SESSION_TTL_S = 12 * 3600
STATE_TTL_S = 600
LOCAL_EMAIL = "local@localhost"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _mac(body: str, secret: str, purpose: str) -> str:
    return hmac.new(secret.encode(), f"{purpose}.{body}".encode(), hashlib.sha256).hexdigest()


def sign(payload: dict[str, Any], secret: str, purpose: str, ttl_s: int) -> str:
    body = _b64(json.dumps({**payload, "exp": int(time.time()) + ttl_s}, separators=(",", ":")).encode())
    return f"{body}.{_mac(body, secret, purpose)}"


def verify(token: str | None, secret: str, purpose: str) -> dict[str, Any] | None:
    if not token or token.count(".") != 1 or not secret:
        return None
    body, mac = token.split(".")
    if not hmac.compare_digest(mac, _mac(body, secret, purpose)):
        return None
    try:
        payload = json.loads(_unb64(body))
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("exp", 0) < time.time():
        return None
    return payload


def _settings(request: Request) -> Settings:
    return request.app.state.settings


def _secure(settings: Settings) -> bool:
    return settings.public_url.startswith("https://")


def _redirect_uri(settings: Settings) -> str:
    return f"{settings.public_url}/api/auth/google/callback"


async def require_admin(request: Request) -> str:
    """The signed-in admin's email; 401 otherwise. The allow-list is re-checked on every request."""
    settings = _settings(request)
    if settings.auth_disabled:
        return LOCAL_EMAIL
    payload = verify(request.cookies.get(SESSION_COOKIE), settings.session_secret, "session")
    email = payload.get("email") if payload else None
    if not isinstance(email, str) or email not in settings.admin_emails:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue")
    return email


def _claims(id_token: str) -> dict[str, Any] | None:
    parts = id_token.split(".")
    if len(parts) != 3:
        return None
    try:
        claims = json.loads(_unb64(parts[1]))
    except ValueError:
        return None
    return claims if isinstance(claims, dict) else None


def _allowed(claims: dict[str, Any], settings: Settings) -> str | None:
    email = str(claims.get("email") or "").strip().lower()
    exp = claims.get("exp")
    checks = (
        claims.get("iss") in ISSUERS,
        claims.get("aud") == settings.google_client_id,
        isinstance(exp, int | float) and exp > time.time(),
        claims.get("email_verified") is True,
        email in settings.admin_emails,
        not settings.workspace_domain or claims.get("hd") == settings.workspace_domain,
    )
    return email if all(checks) else None


def router(transport: httpx.AsyncBaseTransport | None = None) -> APIRouter:
    r = APIRouter(prefix="/api/auth", tags=["auth"])

    def leave(outcome: str | None, settings: Settings) -> RedirectResponse:
        response = RedirectResponse("/" if outcome is None else f"/?auth={outcome}", status_code=307)
        response.delete_cookie(STATE_COOKIE, path="/api/auth")
        return response

    @r.get("/google/start")
    async def google_start(request: Request) -> RedirectResponse:
        settings = _settings(request)
        nonce = secrets.token_urlsafe(24)
        params = {
            "client_id": settings.google_client_id,
            "redirect_uri": _redirect_uri(settings),
            "response_type": "code",
            "scope": "openid email profile",
            "state": nonce,
            "prompt": "select_account",
        }
        if settings.workspace_domain:
            params["hd"] = settings.workspace_domain
        response = RedirectResponse(f"{AUTHORIZE_URL}?{urlencode(params)}", status_code=307)
        response.set_cookie(
            STATE_COOKIE,
            sign({"nonce": nonce}, settings.session_secret, "oauth-state", STATE_TTL_S),
            max_age=STATE_TTL_S,
            httponly=True,
            secure=_secure(settings),
            samesite="lax",
            path="/api/auth",
        )
        return response

    @r.get("/google/callback")
    async def google_callback(
        request: Request, code: str | None = None, state: str | None = None, error: str | None = None
    ) -> RedirectResponse:
        settings = _settings(request)
        saved = verify(request.cookies.get(STATE_COOKIE), settings.session_secret, "oauth-state")
        if error or not code or not state or not saved or not hmac.compare_digest(str(saved.get("nonce")), state):
            log.warning("sign-in refused: missing or mismatched OAuth state")
            return leave("failed", settings)
        try:
            async with httpx.AsyncClient(transport=transport, timeout=10) as http:
                token_response = await http.post(
                    TOKEN_URL,
                    data={
                        "code": code,
                        "client_id": settings.google_client_id,
                        "client_secret": settings.google_client_secret,
                        "redirect_uri": _redirect_uri(settings),
                        "grant_type": "authorization_code",
                    },
                )
            token_response.raise_for_status()
            claims = _claims(str(token_response.json().get("id_token") or ""))
        except (httpx.HTTPError, ValueError):
            log.warning("sign-in failed: Google token exchange did not succeed")
            return leave("failed", settings)
        email = _allowed(claims, settings) if claims else None
        if email is None:
            log.warning("sign-in refused: account not on the access list or token claims invalid")
            return leave("denied", settings)
        response = leave(None, settings)
        response.set_cookie(
            SESSION_COOKIE,
            sign({"email": email}, settings.session_secret, "session", SESSION_TTL_S),
            max_age=SESSION_TTL_S,
            httponly=True,
            secure=_secure(settings),
            samesite="lax",
            path="/",
        )
        return response

    @r.get("/me")
    async def me(request: Request) -> dict[str, Any]:
        email = await require_admin(request)
        return {"email": email, "auth_disabled": _settings(request).auth_disabled}

    @r.post("/logout", status_code=204)
    async def logout() -> Response:
        response = Response(status_code=204)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    return r

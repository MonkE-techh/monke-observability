from __future__ import annotations

import base64
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from monke_admin import auth
from monke_admin.auth import SESSION_COOKIE, STATE_COOKIE, require_admin, sign, verify
from monke_admin.settings import Settings

SETTINGS = Settings(
    google_client_id="cid",
    google_client_secret="gsecret",
    session_secret="x" * 40,
    admin_emails=frozenset({"person@example.com"}),
    public_url="http://testserver",
    app_env="development",
)


def id_token(**overrides) -> str:
    claims = {
        "iss": "https://accounts.google.com",
        "aud": "cid",
        "exp": time.time() + 600,
        "email": "person@example.com",
        "email_verified": True,
        "hd": "monk-e.in",
        **overrides,
    }
    body = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    return f"e30.{body}.sig"


def make_client(settings=SETTINGS, token=None, token_status=200):
    seen = {}

    def google(request: httpx.Request) -> httpx.Response:
        seen["form"] = parse_qs(request.content.decode())
        return httpx.Response(token_status, json={"id_token": token or id_token()})

    app = FastAPI()
    app.state.settings = settings
    app.include_router(auth.router(transport=httpx.MockTransport(google)))

    @app.get("/api/secret")
    async def secret(email: str = Depends(require_admin)):
        return {"email": email}

    return TestClient(app, follow_redirects=False), seen


def sign_in(client) -> httpx.Response:
    start = client.get("/api/auth/google/start")
    state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
    return client.get("/api/auth/google/callback", params={"code": "abc", "state": state})


# --- signing ---------------------------------------------------------------------------------------


def test_signed_value_round_trips():
    token = sign({"email": "a@b.c"}, "k" * 40, "session", ttl_s=60)
    assert verify(token, "k" * 40, "session")["email"] == "a@b.c"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t[:-2] + ("00" if not t.endswith("00") else "11"),  # tampered signature
        lambda t: "x" + t,  # tampered payload
        lambda t: "",  # empty
        lambda t: "not-a-token",
    ],
)
def test_tampered_values_are_rejected(mutate):
    token = sign({"email": "a@b.c"}, "k" * 40, "session", ttl_s=60)
    assert verify(mutate(token), "k" * 40, "session") is None


def test_value_signed_for_another_purpose_or_expired_is_rejected():
    token = sign({"email": "a@b.c"}, "k" * 40, "oauth-state", ttl_s=60)
    assert verify(token, "k" * 40, "session") is None
    expired = sign({"email": "a@b.c"}, "k" * 40, "session", ttl_s=-1)
    assert verify(expired, "k" * 40, "session") is None


# --- flow ------------------------------------------------------------------------------------------


def test_start_redirects_to_google_with_signed_state():
    client, _ = make_client()

    response = client.get("/api/auth/google/start")

    assert response.status_code == 307
    url = urlparse(response.headers["location"])
    params = parse_qs(url.query)
    assert url.netloc == "accounts.google.com"
    assert params["client_id"] == ["cid"]
    assert params["redirect_uri"] == ["http://testserver/api/auth/google/callback"]
    assert params["scope"] == ["openid email profile"]
    assert STATE_COOKIE in response.cookies


def test_successful_sign_in_sets_session_and_grants_access():
    client, seen = make_client()

    response = sign_in(client)

    assert response.status_code == 307 and response.headers["location"] == "/"
    assert seen["form"]["client_secret"] == ["gsecret"]
    assert client.get("/api/secret").json() == {"email": "person@example.com"}
    assert client.get("/api/auth/me").json() == {"email": "person@example.com", "auth_disabled": False}


def test_state_mismatch_is_refused():
    client, _ = make_client()
    client.get("/api/auth/google/start")

    response = client.get("/api/auth/google/callback", params={"code": "abc", "state": "forged"})

    assert response.headers["location"] == "/?auth=failed"
    assert SESSION_COOKIE not in response.cookies


@pytest.mark.parametrize(
    "claims",
    [
        {"email": "stranger@gmail.com"},
        {"email_verified": False},
        {"aud": "someone-else"},
        {"iss": "https://evil.example"},
        {"exp": time.time() - 10},
        {"exp": "soon"},
    ],
)
def test_untrusted_or_unlisted_accounts_are_denied(claims):
    client, _ = make_client(token=id_token(**claims))

    response = sign_in(client)

    assert response.headers["location"] == "/?auth=denied"
    assert client.get("/api/secret").status_code == 401


def test_workspace_domain_is_enforced_when_set():
    settings = Settings(**{**SETTINGS.__dict__, "workspace_domain": "monk-e.in"})
    client, _ = make_client(settings=settings, token=id_token(hd="other.com"))

    assert sign_in(client).headers["location"] == "/?auth=denied"


def test_google_token_error_fails_sign_in():
    client, _ = make_client(token_status=400)

    assert sign_in(client).headers["location"] == "/?auth=failed"


def test_email_removed_from_allow_list_loses_access():
    client, _ = make_client()
    sign_in(client)
    client.app.state.settings = Settings(**{**SETTINGS.__dict__, "admin_emails": frozenset({"other@example.com"})})

    assert client.get("/api/secret").status_code == 401


def test_forged_session_cookie_is_rejected():
    client, _ = make_client()
    forged = sign({"email": "person@example.com"}, "y" * 40, "session", ttl_s=600)
    client.cookies.set(SESSION_COOKIE, forged)

    assert client.get("/api/secret").status_code == 401


def test_logout_clears_the_session():
    client, _ = make_client()
    sign_in(client)

    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/secret").status_code == 401


def test_auth_disabled_signs_in_as_local_user():
    settings = Settings(auth_disabled=True, app_env="development")
    client, _ = make_client(settings=settings)

    assert client.get("/api/secret").json() == {"email": "local@localhost"}

"""Configuration from the environment. Secret values are held here and never returned or logged."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

MIN_SESSION_SECRET = 32
DEFAULT_APPS_FILE = Path(__file__).resolve().parents[4] / "apps.yaml"


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    posthog_api_key: str = field(default="", repr=False)
    posthog_project_id: str = ""
    posthog_app_host: str = "https://eu.posthog.com"
    google_client_id: str = ""
    google_client_secret: str = field(default="", repr=False)
    session_secret: str = field(default="", repr=False)
    admin_emails: frozenset[str] = frozenset()
    workspace_domain: str = ""
    public_url: str = ""
    app_env: str = "production"
    auth_disabled: bool = False
    apps_file: Path = DEFAULT_APPS_FILE

    @classmethod
    def from_env(cls) -> Settings:
        app_env = os.environ.get("APP_ENV", "production").strip() or "production"
        auth_disabled = _flag(os.environ.get("AUTH_DISABLED"))
        if auth_disabled and app_env == "production":
            raise ValueError("AUTH_DISABLED is for local development only and is refused when APP_ENV=production")
        emails = os.environ.get("ADMIN_EMAILS", "")
        return cls(
            posthog_api_key=os.environ.get("POSTHOG_PERSONAL_API_KEY", "").strip(),
            posthog_project_id=os.environ.get("POSTHOG_PROJECT_ID", "").strip(),
            posthog_app_host=(os.environ.get("POSTHOG_APP_HOST") or "https://eu.posthog.com").strip().rstrip("/"),
            google_client_id=os.environ.get("GOOGLE_CLIENT_ID", "").strip(),
            google_client_secret=os.environ.get("GOOGLE_CLIENT_SECRET", "").strip(),
            session_secret=os.environ.get("SESSION_SECRET", ""),
            admin_emails=frozenset(e.strip().lower() for e in emails.split(",") if e.strip()),
            workspace_domain=os.environ.get("GOOGLE_WORKSPACE_DOMAIN", "").strip().lower(),
            public_url=os.environ.get("PUBLIC_URL", "").strip().rstrip("/"),
            app_env=app_env,
            auth_disabled=auth_disabled,
            apps_file=Path(os.environ.get("APPS_FILE") or DEFAULT_APPS_FILE),
        )

    @property
    def posthog_configured(self) -> bool:
        return bool(self.posthog_api_key and self.posthog_project_id)

    def missing(self) -> list[str]:
        """Names of required variables that are not set (never their values)."""
        missing = [
            name
            for name, value in (
                ("POSTHOG_PERSONAL_API_KEY", self.posthog_api_key),
                ("POSTHOG_PROJECT_ID", self.posthog_project_id),
            )
            if not value
        ]
        if self.auth_disabled:
            return missing
        for name, value in (
            ("GOOGLE_CLIENT_ID", self.google_client_id),
            ("GOOGLE_CLIENT_SECRET", self.google_client_secret),
            ("ADMIN_EMAILS", self.admin_emails),
            ("PUBLIC_URL", self.public_url),
        ):
            if not value:
                missing.append(name)
        if not self.session_secret:
            missing.append("SESSION_SECRET")
        elif len(self.session_secret) < MIN_SESSION_SECRET:
            missing.append(f"SESSION_SECRET (at least {MIN_SESSION_SECRET} characters)")
        return missing

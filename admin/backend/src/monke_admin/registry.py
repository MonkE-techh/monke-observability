"""The app registry (`apps.yaml` at the repo root): the apps the admin page always lists."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_APP_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def valid_app_name(name: object) -> bool:
    return isinstance(name, str) and len(name) <= 64 and bool(_APP_NAME.match(name))


@dataclass(frozen=True)
class AppEntry:
    name: str
    uses_llm: bool = False
    status: str = "planned"


def load_registry(path: Path) -> list[AppEntry]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    apps: list[AppEntry] = []
    for raw in data.get("apps") or []:
        name = raw.get("name")
        if not valid_app_name(name):
            raise ValueError(f"{path}: app name {name!r} is not kebab-case")
        apps.append(AppEntry(name=name, uses_llm=bool(raw.get("uses_llm")), status=str(raw.get("status") or "planned")))
    return apps

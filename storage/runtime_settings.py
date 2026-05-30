from __future__ import annotations

import json
from pathlib import Path

from core.config import ROOT_DIR

RUNTIME_PATH = ROOT_DIR / "data" / "runtime_settings.json"


def load_runtime() -> dict:
    if not RUNTIME_PATH.exists():
        return {}
    try:
        return json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def save_runtime(data: dict) -> None:
    RUNTIME_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def human_confirm_enabled(default: bool = True) -> bool:
    data = load_runtime()
    if "human_confirm_enabled" in data:
        return bool(data["human_confirm_enabled"])
    return default


def set_human_confirm_enabled(enabled: bool) -> None:
    data = load_runtime()
    data["human_confirm_enabled"] = enabled
    save_runtime(data)

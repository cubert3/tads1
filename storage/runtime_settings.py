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


def get_camera_config() -> dict:
    data = load_runtime()
    return {
        "name": data.get("camera_name", "ESP32-CAM · Junction A"),
        "url": data.get("camera_url", ""),
        "url_masked": _mask_url(data.get("camera_url", "")),
    }


def set_camera_config(name: str, url: str) -> None:
    data = load_runtime()
    data["camera_name"] = name
    data["camera_url"] = url
    save_runtime(data)


def set_detection_tuning(proximity_px: float, confirm_frames: int, iou_threshold: float) -> None:
    from core.config import get_settings

    data = load_runtime()
    data["proximity_px"] = proximity_px
    data["confirm_frames"] = confirm_frames
    data["collision_iou_threshold"] = iou_threshold
    save_runtime(data)
    get_settings.cache_clear()


def get_detection_tuning(defaults) -> dict:
    data = load_runtime()
    return {
        "proximity_px": float(data.get("proximity_px", defaults.near_miss.proximity_px)),
        "confirm_frames": int(data.get("confirm_frames", defaults.collision.confirm_frames)),
        "collision_iou_threshold": float(
            data.get("collision_iou_threshold", defaults.collision.iou_threshold)
        ),
    }


def _mask_url(url: str) -> str:
    if not url:
        return "Not configured"
    if "@" in url:
        parts = url.split("@", 1)
        return f"{parts[0].split('//')[0]}//***@{parts[1]}"
    if len(url) > 40:
        return url[:24] + "…" + url[-8:]
    return url

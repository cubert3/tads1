from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_PATH = ROOT_DIR / "config" / "settings.yaml"


class DetectionConfig(BaseModel):
    model: str = "yolov8n.pt"
    conf: float = 0.35
    imgsz: int = 640
    device: str = "cpu"


class TrackingConfig(BaseModel):
    backend: str = "botsort"
    persist: bool = True


class NearMissConfig(BaseModel):
    proximity_px: float = 80.0
    approach_rate_min: float = 2.0


class CollisionConfig(BaseModel):
    iou_threshold: float = 0.25
    decel_threshold: float = 0.40
    min_signals: int = 2
    confirm_frames: int = 3
    cooldown_seconds: float = 10.0
    cooldown_distance_px: float = 100.0


class ClipFilterConfig(BaseModel):
    enabled: bool = False
    reject_margin: float = 0.05
    model_name: str = "openai/clip-vit-base-patch32"
    prompts: dict[str, str] = Field(
        default_factory=lambda: {
            "accident": "car accident on road",
            "normal": "normal traffic",
            "stopped": "cars stopped at traffic lights",
        }
    )


class CalibrationConfig(BaseModel):
    enabled: bool = False
    meters_per_pixel: float | None = None
    reference_points: list[list[float]] = Field(default_factory=list)


class EvidenceConfig(BaseModel):
    pre_seconds: float = 5.0
    post_seconds: float = 10.0


class AlertsConfig(BaseModel):
    webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_to: str | None = None
    smtp_enabled: bool = False


class PerformanceConfig(BaseModel):
    optical_flow_interval: int = 3
    half_precision: bool = False
    save_annotated_video: bool = True
    show_overlay: bool = True


class PathsConfig(BaseModel):
    samples_dir: str = "data/samples"
    incidents_dir: str = "data/incidents"
    output_dir: str = "output/annotated"
    database_path: str = "data/incidents.db"


class LocationConfig(BaseModel):
    latitude: float = 13.6288
    longitude: float = 79.4192
    label: str = "Demo Junction"


class DispatchNumbersConfig(BaseModel):
    police_number: str | None = None
    ambulance_number: str | None = None


class SeverityRoutingConfig(BaseModel):
    near_miss: str = "log_only"
    collision: str = "police"
    severe: str = "police_and_ambulance"


class RoadSosConfig(BaseModel):
    human_confirm_enabled: bool = True
    plate_detection_enabled: bool = True
    location: LocationConfig = Field(default_factory=LocationConfig)
    dispatch: DispatchNumbersConfig = Field(default_factory=DispatchNumbersConfig)
    severity_routing: SeverityRoutingConfig = Field(default_factory=SeverityRoutingConfig)


class Settings(BaseModel):
    detection: DetectionConfig = Field(default_factory=DetectionConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    near_miss: NearMissConfig = Field(default_factory=NearMissConfig)
    collision: CollisionConfig = Field(default_factory=CollisionConfig)
    clip_filter: ClipFilterConfig = Field(default_factory=ClipFilterConfig)
    calibration: CalibrationConfig = Field(default_factory=CalibrationConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    performance: PerformanceConfig = Field(default_factory=PerformanceConfig)
    road_sos: RoadSosConfig = Field(default_factory=RoadSosConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    def resolve_path(self, relative: str) -> Path:
        path = Path(relative)
        return path if path.is_absolute() else ROOT_DIR / path


def _apply_runtime_overrides(settings: Settings) -> Settings:
    try:
        from storage.runtime_settings import load_runtime

        r = load_runtime()
    except Exception:
        return settings
    if "proximity_px" in r:
        settings.near_miss.proximity_px = float(r["proximity_px"])
    if "confirm_frames" in r:
        settings.collision.confirm_frames = int(r["confirm_frames"])
    if "collision_iou_threshold" in r:
        settings.collision.iou_threshold = float(r["collision_iou_threshold"])
    return settings


@lru_cache
def get_settings(config_path: str | None = None) -> Settings:
    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    raw: dict[str, Any] = {}
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
    return _apply_runtime_overrides(Settings.model_validate(raw))

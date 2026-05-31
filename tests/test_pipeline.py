from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.performance import estimate_pipeline_fps


def test_settings_load():
    settings = get_settings()
    assert settings.detection.model.endswith(".pt")
    assert settings.performance.optical_flow_interval >= 1


def test_performance_estimate_cpu():
    est = estimate_pipeline_fps("yolov8n.pt", "cpu", 1280, 720, 25.0, optical_flow_interval=3)
    assert est.estimated_pipeline_fps > 0
    assert est.estimated_realtime_factor > 0


def test_performance_estimate_interval_improves_fps():
    every_frame = estimate_pipeline_fps("yolov8n.pt", "cpu", 1280, 720, 25.0, optical_flow_interval=1)
    every_third = estimate_pipeline_fps("yolov8n.pt", "cpu", 1280, 720, 25.0, optical_flow_interval=3)
    assert every_third.estimated_pipeline_fps >= every_frame.estimated_pipeline_fps

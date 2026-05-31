from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.performance import estimate_pipeline_fps, format_estimate


def test_estimate_returns_notes():
    est = estimate_pipeline_fps("yolov8n.pt", "cpu")
    assert len(est.notes) >= 1
    text = format_estimate(est)
    assert "Estimated pipeline throughput" in text

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import DetectionConfig
from core.detector import ALL_TARGET_CLASSES, Detection, VehicleDetector


def test_detection_dataclass():
    det = Detection(bbox=(10.0, 20.0, 50.0, 60.0), confidence=0.9, class_id=2, class_name="car")
    assert det.class_name == "car"
    assert det.confidence == pytest.approx(0.9)


def test_target_classes_include_vehicles_and_person():
    assert 2 in ALL_TARGET_CLASSES  # car
    assert 0 in ALL_TARGET_CLASSES  # person


@pytest.mark.slow
def test_detector_on_synthetic_frame():
    """Runs YOLO if weights are available; skips otherwise."""
    weights = Path("yolov8n.pt")
    if not weights.exists():
        pytest.skip("yolov8n.pt not downloaded — run scripts/download_weights.py")

    detector = VehicleDetector(DetectionConfig(model="yolov8n.pt", device="cpu"))
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    # Draw a simple rectangle so the frame is not completely empty
    frame[200:280, 250:390] = (128, 128, 128)

    results = detector.detect(frame)
    assert isinstance(results, list)

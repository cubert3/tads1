from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.collision import CollisionScorer, approach_rate, center_distance, compute_iou
from core.config import CollisionConfig, NearMissConfig
from core.motion import MotionAnalyzer, MotionSnapshot, TrackState


def test_iou_full_overlap():
    box = (0.0, 0.0, 100.0, 100.0)
    assert compute_iou(box, box) == pytest.approx(1.0)


def test_iou_no_overlap():
    a = (0.0, 0.0, 50.0, 50.0)
    b = (100.0, 100.0, 150.0, 150.0)
    assert compute_iou(a, b) == 0.0


def test_center_distance():
    a = (0.0, 0.0, 10.0, 10.0)
    b = (10.0, 0.0, 20.0, 10.0)
    assert center_distance(a, b) == pytest.approx(10.0)


def test_approach_rate_closing():
    ca, cb = (0.0, 0.0), (10.0, 0.0)
    va, vb = (2.0, 0.0), (-2.0, 0.0)
    assert approach_rate(ca, cb, va, vb) > 0


def test_near_miss_detection():
    motion = MotionAnalyzer()
    scorer = CollisionScorer(CollisionConfig(), NearMissConfig(proximity_px=100, approach_rate_min=1.0), motion)
    a = MotionSnapshot(1, (50.0, 50.0), (5.0, 0.0), 5.0, 0.0, 0.0, (40.0, 40.0, 60.0, 60.0), [(50.0, 50.0)])
    b = MotionSnapshot(2, (90.0, 50.0), (-5.0, 0.0), 5.0, 0.0, 0.0, (80.0, 40.0, 100.0, 60.0), [(90.0, 50.0)])
    events = scorer.evaluate([a, b], 10, 0.4, 1.0, 1.0)
    assert any(e.event_type == "near_miss" for e in events)


def test_collision_overlap_and_decel():
    motion = MotionAnalyzer()
    motion.tracks[1] = TrackState(speeds=deque([20.0, 20.0, 20.0, 20.0, 20.0, 2.0], maxlen=30))
    motion.tracks[2] = TrackState(speeds=deque([15.0, 15.0, 15.0, 15.0, 15.0, 1.0], maxlen=30))
    scorer = CollisionScorer(CollisionConfig(min_signals=2, decel_threshold=0.5), NearMissConfig(), motion)
    box = (100.0, 100.0, 200.0, 200.0)
    a = MotionSnapshot(1, (150.0, 150.0), (0.0, 0.0), 0.0, 0.0, 120.0, box, [(150.0, 150.0)])
    b = MotionSnapshot(2, (155.0, 155.0), (0.0, 0.0), 0.0, 0.0, 100.0, box, [(155.0, 155.0)])
    events = scorer.evaluate([a, b], 20, 0.8, 5.0, 2.0)
    assert any(e.event_type == "collision" for e in events)

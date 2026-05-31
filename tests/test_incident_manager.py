from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.clip_filter import ClipFalsePositiveFilter
from core.collision import ScoredEvent
from core.config import ClipFilterConfig, CollisionConfig
from core.incident_manager import IncidentManager, IncidentState


@pytest.fixture
def manager() -> IncidentManager:
    clip = ClipFalsePositiveFilter(ClipFilterConfig(enabled=False))
    return IncidentManager(CollisionConfig(confirm_frames=3), clip, human_confirm_enabled=True)


@pytest.fixture
def manager_auto() -> IncidentManager:
    clip = ClipFalsePositiveFilter(ClipFilterConfig(enabled=False))
    return IncidentManager(CollisionConfig(confirm_frames=3), clip, human_confirm_enabled=False)


def _event(score: float = 0.5, frame: int = 1) -> ScoredEvent:
    return ScoredEvent(
        event_type="collision",
        severity="collision",
        score=score,
        signals=["overlap", "decel"],
        track_ids=(1, 2),
        location=(100.0, 100.0),
        frame_index=frame,
        timestamp_sec=frame / 25.0,
    )


def test_incident_pending_review_after_consecutive_frames(manager: IncidentManager):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    assert manager.process_events([_event(frame=1)], frame) == []
    assert manager.process_events([_event(frame=2)], frame) == []
    pending = manager.process_events([_event(frame=3)], frame)
    assert len(pending) == 1
    assert pending[0].state == IncidentState.PENDING_REVIEW


def test_incident_auto_confirms_without_human_review(manager_auto: IncidentManager):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    manager_auto.process_events([_event(frame=1)], frame)
    manager_auto.process_events([_event(frame=2)], frame)
    confirmed = manager_auto.process_events([_event(frame=3)], frame)
    assert len(confirmed) == 1
    assert confirmed[0].state == IncidentState.CONFIRMED


def test_incident_resets_if_event_stops(manager: IncidentManager):
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    manager.process_events([_event(frame=1)], frame)
    manager.process_events([_event(frame=2)], frame)
    manager.process_events([], frame)
    manager.process_events([], frame)
    manager.process_events([], frame)
    confirmed = manager.process_events([_event(frame=10)], frame)
    assert confirmed == []
    assert len(manager._active) == 1
    assert manager._active[list(manager._active.keys())[0]].candidate_frames == 1


def test_incident_not_decayed_on_same_frame_as_update(manager: IncidentManager):
    """Regression: candidate count must not decrement on frames where the event fired."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    for i in range(1, 4):
        result = manager.process_events([_event(frame=i)], frame)
        if i < 3:
            assert result == []
    assert len(manager.all_incidents) == 1
    assert manager.all_incidents[0].state == IncidentState.PENDING_REVIEW

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import RoadSosConfig, SeverityRoutingConfig
from core.cooldown_tracker import CooldownTracker
from core.incident_manager import IncidentRecord, IncidentState
from media.dispatch import DispatchService


def _record(severity: str) -> IncidentRecord:
    return IncidentRecord(
        id="test-id",
        state=IncidentState.CONFIRMED,
        event_type="collision" if severity != "near_miss" else "near_miss",
        severity=severity,
        score=0.8,
        signals=["overlap"],
        track_ids=(1, 2),
        location=(100.0, 200.0),
        frame_index=10,
        timestamp_sec=1.5,
        plate_numbers=["TN01AB1234"],
        latitude=13.6,
        longitude=79.4,
        location_label="Demo",
    )


def test_severity_routing_near_miss_log_only():
    road = RoadSosConfig(severity_routing=SeverityRoutingConfig())
    svc = DispatchService(road)
    actions = svc.plan_actions(_record("near_miss"))
    assert actions == [("log", "dashboard", "incident_log")]


def test_severity_routing_collision_police():
    road = RoadSosConfig()
    road.dispatch.police_number = "+91111"
    svc = DispatchService(road)
    actions = svc.plan_actions(_record("collision"))
    assert ("notify_police", "phone", "+91111") in actions


def test_severity_routing_severe_both():
    road = RoadSosConfig()
    road.dispatch.police_number = "+91111"
    road.dispatch.ambulance_number = "+91222"
    svc = DispatchService(road)
    actions = svc.plan_actions(_record("severe"))
    assert ("notify_police", "phone", "+91111") in actions
    assert ("notify_ambulance", "phone", "+91222") in actions


def test_cooldown_tracker_active_zones():
    tracker = CooldownTracker(cooldown_seconds=10.0, cooldown_distance_px=50.0)
    tracker.record_alert(10.0, 20.0, "inc-1")
    zones = tracker.active_zones()
    assert len(zones) == 1
    assert zones[0].reason == "alert"

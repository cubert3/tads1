"""Populate SQLite with demo incidents, dispatch log, and cooldown zones for hackathon UI."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from core.config import get_settings
from core.incident_manager import IncidentRecord, IncidentState
from media.dispatch import DispatchEntry, DispatchService
from storage.incident_store import IncidentStore


async def seed_demo_data(db_path: Path | None = None, force: bool = False) -> dict[str, int]:
    settings = get_settings()
    path = db_path or settings.resolve_path(settings.paths.database_path)
    store = IncidentStore(path)

    existing = await store.list_all()
    if existing and not force:
        return {"skipped": 1, "incidents": len(existing)}

    now = time.time()
    loc = settings.road_sos.location
    incidents_dir = settings.resolve_path(settings.paths.incidents_dir)
    incidents_dir.mkdir(parents=True, exist_ok=True)

    demo_incidents = [
        IncidentRecord(
            id="demo-pending-001",
            state=IncidentState.PENDING_REVIEW,
            event_type="collision",
            severity="collision",
            score=0.72,
            signals=["overlap", "decel", "convergence"],
            track_ids=(3, 7),
            location=(412.0, 288.0),
            frame_index=1420,
            timestamp_sec=47.3,
            confirmed_at=now - 120,
            dispatch_status="awaiting_human",
            plate_numbers=["TN09AB4521"],
            latitude=loc.latitude,
            longitude=loc.longitude,
            location_label=loc.label,
            source_video="demo_cctv_junction_a.mp4",
            human_reviewed=False,
        ),
        IncidentRecord(
            id="demo-confirmed-002",
            state=IncidentState.CONFIRMED,
            event_type="collision",
            severity="severe",
            score=0.89,
            signals=["overlap", "decel", "track_loss"],
            track_ids=(1, 5),
            location=(220.0, 340.0),
            frame_index=890,
            timestamp_sec=29.6,
            confirmed_at=now - 3600,
            dispatch_status="simulated",
            plate_numbers=["KA01MN8820", "TN22CX1098"],
            latitude=loc.latitude + 0.002,
            longitude=loc.longitude - 0.001,
            location_label=loc.label,
            source_video="demo_cctv_junction_a.mp4",
            human_reviewed=True,
        ),
        IncidentRecord(
            id="demo-nearmiss-003",
            state=IncidentState.CONFIRMED,
            event_type="near_miss",
            severity="near_miss",
            score=0.41,
            signals=["convergence"],
            track_ids=(8, 12),
            location=(580.0, 190.0),
            frame_index=2100,
            timestamp_sec=70.0,
            confirmed_at=now - 7200,
            dispatch_status="logged",
            plate_numbers=[],
            latitude=loc.latitude - 0.001,
            longitude=loc.longitude + 0.002,
            location_label=loc.label,
            source_video="demo_cctv_junction_b.mp4",
            human_reviewed=True,
        ),
        IncidentRecord(
            id="demo-dismissed-004",
            state=IncidentState.DISMISSED,
            event_type="collision",
            severity="collision",
            score=0.38,
            signals=["decel"],
            track_ids=(2, 4),
            location=(100.0, 400.0),
            frame_index=450,
            timestamp_sec=15.0,
            confirmed_at=now - 18000,
            dispatch_status="dismissed",
            plate_numbers=[],
            latitude=loc.latitude,
            longitude=loc.longitude,
            location_label=loc.label,
            source_video="demo_merge_traffic.mp4",
            human_reviewed=True,
        ),
    ]

    for record in demo_incidents:
        meta_path = incidents_dir / f"{record.id}.json"
        meta_path.write_text(
            json.dumps(
                {
                    "id": record.id,
                    "demo": True,
                    "severity": record.severity,
                    "signals": record.signals,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        await store.save(record)

    dispatch_svc = DispatchService(settings.road_sos)
    entries: list[DispatchEntry] = []
    for record in demo_incidents:
        if record.state == IncidentState.PENDING_REVIEW:
            continue
        planned = dispatch_svc.plan_actions(record)
        for action, channel, target in planned:
            entries.append(
                DispatchEntry(
                    id=str(uuid.uuid4()),
                    incident_id=record.id,
                    channel=channel,
                    target=target,
                    severity=record.severity,
                    action=action,
                    status="simulated" if channel == "phone" else "logged",
                    message=dispatch_svc.build_message(record),
                    created_at=record.confirmed_at or now,
                )
            )
    await store.save_dispatch_entries(entries)

    zones = [
        {
            "id": str(uuid.uuid4()),
            "x": 412.0,
            "y": 288.0,
            "radius_px": settings.collision.cooldown_distance_px,
            "reason": "alert",
            "incident_id": "demo-pending-001",
            "created_at": now - 30,
            "expires_at": now + settings.collision.cooldown_seconds - 30,
        },
        {
            "id": str(uuid.uuid4()),
            "x": 220.0,
            "y": 340.0,
            "radius_px": settings.collision.cooldown_distance_px,
            "reason": "alert",
            "incident_id": "demo-confirmed-002",
            "created_at": now - 5,
            "expires_at": now + settings.collision.cooldown_seconds - 5,
        },
        {
            "id": str(uuid.uuid4()),
            "x": 350.0,
            "y": 300.0,
            "radius_px": settings.collision.cooldown_distance_px,
            "reason": "blocked",
            "incident_id": None,
            "created_at": now - 8,
            "expires_at": now + settings.collision.cooldown_seconds - 8,
        },
    ]

    conn = await store.db.connect()
    try:
        for z in zones:
            await conn.execute(
                """
                INSERT OR REPLACE INTO cooldown_zones
                (id, x, y, radius_px, reason, incident_id, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    z["id"],
                    z["x"],
                    z["y"],
                    z["radius_px"],
                    z["reason"],
                    z["incident_id"],
                    z["created_at"],
                    z["expires_at"],
                ),
            )
        await conn.commit()
    finally:
        await conn.close()

    return {
        "incidents": len(demo_incidents),
        "dispatch": len(entries),
        "cooldown_zones": len(zones),
    }


def seed_demo_sync(force: bool = False) -> dict[str, int]:
    settings = get_settings()
    return asyncio.run(seed_demo_data(settings.resolve_path(settings.paths.database_path), force=force))

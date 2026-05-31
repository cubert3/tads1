"""Persist last pipeline run summary for dashboard hero."""

from __future__ import annotations

import json
import time
from pathlib import Path

from dashboard.utils import pick_primary_incident

ROOT = Path(__file__).resolve().parents[1]
SUMMARY_PATH = ROOT / "data" / "last_run_summary.json"


def write_run_summary(
    *,
    source_video: str,
    output_name: str | None,
    incidents: list,
    frames: int,
    fps: float,
) -> None:
    rows = [
        {
            "id": inc.id,
            "severity": inc.severity,
            "event_type": inc.event_type,
            "score": inc.score,
            "timestamp_sec": inc.timestamp_sec,
            "state": inc.state.value if hasattr(inc.state, "value") else str(inc.state),
            "created_at": getattr(inc, "created_at", time.time()),
        }
        for inc in incidents
    ]
    primary = pick_primary_incident(rows)
    payload = {
        "finished_at": time.time(),
        "source_video": source_video,
        "output_name": output_name,
        "frames": frames,
        "fps": fps,
        "incident_count": len(rows),
        "primary_incident_id": primary["id"] if primary else None,
    }
    SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


def read_run_summary() -> dict | None:
    if not SUMMARY_PATH.exists():
        return None
    try:
        return json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None

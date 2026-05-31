"""Dashboard helpers."""

from __future__ import annotations

import time
from pathlib import Path


def normalize_dispatch_status(raw: str | None) -> str:
    if not raw:
        return "pending"
    s = raw.lower()
    if s in ("pending", "awaiting_human", "queued", "awaiting"):
        return "pending"
    if s in ("called", "simulated", "sent", "logged", "dispatched"):
        return "called"
    if s in ("resolved", "dismissed", "closed"):
        return "resolved"
    return "pending"


def ops_status(
    pending_count: int,
    cooldown_count: int,
    last_dispatch_at: float | None,
    pipeline_busy: bool,
) -> str:
    if pipeline_busy:
        return "MONITORING"
    if cooldown_count > 0 and pending_count == 0:
        return "COOLDOWN"
    if pending_count > 0:
        return "INCIDENT"
    if last_dispatch_at and (time.time() - last_dispatch_at) < 300:
        return "DISPATCHED"
    return "MONITORING"


def find_preview_image(incidents_dir: Path, output_dir: Path) -> Path | None:
    live = Path(incidents_dir).parent / "live_preview.jpg"
    if live.exists():
        return live
    candidates: list[Path] = []
    if incidents_dir.exists():
        candidates.extend(incidents_dir.glob("*_keyframe.jpg"))
    if output_dir.exists():
        for mp4 in sorted(output_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)[:1]:
            candidates.append(mp4)
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def format_video_time(seconds: float) -> str:
    s = int(max(0, seconds))
    m, sec = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def pick_primary_incident(incidents: list[dict]) -> dict | None:
    """Best single event to show the operator (severe/collision preferred)."""
    if not incidents:
        return None
    severity_rank = {"severe": 4, "collision": 3, "near_miss": 2}

    def rank(item: dict) -> tuple:
        sev = item.get("severity", "")
        return (
            severity_rank.get(sev, 1),
            float(item.get("score", 0)),
            float(item.get("timestamp_sec", 0)),
        )

    collisions = [
        i
        for i in incidents
        if i.get("severity") in ("severe", "collision", "near_miss")
        or i.get("event_type") in ("collision", "near_miss")
    ]
    pool = collisions or incidents
    return max(pool, key=rank)


def parse_pipeline_fps(log_path: Path) -> float | None:
    if not log_path.exists():
        return None
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in reversed(text.splitlines()):
        if "frames @" in line and "FPS" in line:
            part = line.split("@")[-1].strip()
            try:
                return float(part.replace("FPS", "").strip())
            except ValueError:
                pass
    return None

"""Optional FastAPI client for Upload & test lab."""

from __future__ import annotations

from pathlib import Path

import httpx

DEFAULT_API = "http://127.0.0.1:8000"


def api_reachable(base: str = DEFAULT_API) -> bool:
    try:
        r = httpx.get(f"{base.rstrip('/')}/api/health", timeout=2.0)
        return r.status_code == 200
    except Exception:
        return False


def upload_video(path: Path, base: str = DEFAULT_API) -> dict:
    with path.open("rb") as f:
        files = {"file": (path.name, f, "video/mp4")}
        r = httpx.post(f"{base.rstrip('/')}/api/videos/upload", files=files, timeout=120.0)
    r.raise_for_status()
    return r.json()


def start_process(video_id: str, base: str = DEFAULT_API) -> dict:
    r = httpx.post(f"{base.rstrip('/')}/api/videos/{video_id}/process", timeout=30.0)
    r.raise_for_status()
    return r.json()


def job_status(job_id: str, base: str = DEFAULT_API) -> dict:
    r = httpx.get(f"{base.rstrip('/')}/api/jobs/{job_id}/status", timeout=10.0)
    r.raise_for_status()
    return r.json()

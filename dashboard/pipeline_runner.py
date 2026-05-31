"""Run video pipeline in a subprocess so Streamlit stays connected."""

from __future__ import annotations

import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
_JOB_META = ROOT / "data" / "pipeline_job.json"
_LOG_PATH = ROOT / "data" / "pipeline_last_run.log"

_ACTIVE_JOBS: dict[int, subprocess.Popen] = {}

JobState = Literal["idle", "running", "success", "failed"]

_PROGRESS_RE = re.compile(r"Progress:\s*(\d+)\s*/\s*(\d+)\s*frames?\s*\(([\d.]+)\s*fps\)", re.I)


def _write_job_meta(meta: dict) -> None:
    _JOB_META.parent.mkdir(parents=True, exist_ok=True)
    _JOB_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _read_job_meta() -> dict:
    if not _JOB_META.exists():
        return {}
    try:
        return json.loads(_JOB_META.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def update_job_progress(frames_done: int, frames_total: int, fps: float) -> None:
    meta = _read_job_meta()
    meta.update(
        {
            "frames_done": frames_done,
            "frames_total": frames_total,
            "fps_current": round(fps, 2),
            "progress_updated": time.time(),
        }
    )
    _write_job_meta(meta)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _log_tail(n: int = 8000) -> str:
    if not _LOG_PATH.exists():
        return ""
    try:
        return _LOG_PATH.read_text(encoding="utf-8", errors="replace")[-n:]
    except OSError:
        return ""


def _log_shows_done() -> bool:
    tail = _log_tail(4000)
    if "Done —" in tail and "frames" in tail:
        return True
    if "Incidents:" in tail and "Progress:" in tail:
        return True
    return False


def parse_pipeline_progress() -> dict | None:
    """Read frame progress from job meta or pipeline log."""
    meta = _read_job_meta()
    done = meta.get("frames_done")
    total = meta.get("frames_total")
    if isinstance(done, int) and isinstance(total, int) and total > 0:
        return {
            "done": done,
            "total": total,
            "fps": float(meta.get("fps_current") or 0),
            "pct": min(1.0, done / total),
        }

    tail = _log_tail(6000)
    matches = _PROGRESS_RE.findall(tail)
    if matches:
        d, t, fps = matches[-1]
        done_i, total_i = int(d), int(t)
        if total_i > 0:
            return {
                "done": done_i,
                "total": total_i,
                "fps": float(fps),
                "pct": min(1.0, done_i / total_i),
            }
    return None


def cancel_pipeline_job(session_state) -> None:
    pid = session_state.get("pipeline_pid") or _read_job_meta().get("pid")
    if pid:
        proc = _ACTIVE_JOBS.pop(int(pid), None)
        if proc is not None and proc.poll() is None:
            proc.terminate()
        elif pid_alive(int(pid)):
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/PID", str(pid), "/F"],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                else:
                    os.kill(int(pid), signal.SIGTERM)
            except OSError:
                pass
    meta = _read_job_meta()
    meta["status"] = "cancelled"
    _write_job_meta(meta)
    session_state.pop("pipeline_pid", None)
    session_state.pipeline_busy = False
    session_state.pop("pipeline_done_out", None)
    session_state.pipeline_error = True


def sync_pipeline_session(session_state, output_dir: Path) -> None:
    """Recover UI state after Streamlit reload or subprocess exit."""
    meta = _read_job_meta()
    if not meta:
        return

    pid = meta.get("pid")
    status = meta.get("status")
    out_name = meta.get("output") or session_state.get("pipeline_out")

    if status == "running" and pid and pid_alive(int(pid)):
        if not session_state.get("pipeline_pid"):
            session_state.pipeline_pid = int(pid)
            session_state.pipeline_busy = True
            session_state.pipeline_source_video = meta.get("video") or session_state.get("pipeline_source_video")
            session_state.pipeline_out = out_name
        return

    if status == "success" and not session_state.get("pipeline_done_out"):
        session_state.pipeline_done_out = out_name
        session_state.pop("pipeline_pid", None)
        session_state.pipeline_busy = False
        session_state.pop("pipeline_error", None)
        session_state.show_collision_hero = True
        return

    if status in ("failed", "cancelled"):
        session_state.pop("pipeline_pid", None)
        session_state.pipeline_busy = False
        if not session_state.get("pipeline_done_out"):
            session_state.pipeline_error = True


def start_pipeline_job(video_path: Path, output_name: str) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_video.py"),
        "--input",
        str(video_path),
        "--output",
        output_name,
    ]
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    log_handle = _LOG_PATH.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    _ACTIVE_JOBS[proc.pid] = proc
    _write_job_meta(
        {
            "pid": proc.pid,
            "output": output_name,
            "video": str(video_path),
            "started": time.time(),
            "status": "running",
            "frames_done": 0,
            "frames_total": 0,
        }
    )
    return proc.pid


def _finish_job(session_state, pid: int, code: int, output_dir: Path) -> JobState:
    _ACTIVE_JOBS.pop(pid, None)
    session_state.pop("pipeline_pid", None)
    session_state.pipeline_busy = False

    meta = _read_job_meta()
    out_name = meta.get("output") or session_state.get("pipeline_out", "dashboard_test.mp4")

    if code != 0:
        session_state.pipeline_error = True
        meta["status"] = "failed"
        meta["exit_code"] = code
        _write_job_meta(meta)
        return "failed"

    session_state.pipeline_done_out = out_name
    session_state.pop("pipeline_error", None)
    meta["status"] = "success"
    meta["exit_code"] = 0
    _write_job_meta(meta)
    return "success"


def check_pipeline_job(session_state, output_dir: Path) -> JobState:
    pid = session_state.get("pipeline_pid")
    if not pid:
        sync_pipeline_session(session_state, output_dir)
        if session_state.get("pipeline_done_out"):
            return "success"
        if session_state.get("pipeline_error"):
            return "failed"
        return "idle"

    proc = _ACTIVE_JOBS.get(int(pid))
    if proc is not None:
        code = proc.poll()
        if code is None:
            return "running"
        return _finish_job(session_state, int(pid), code, output_dir)

    if pid_alive(int(pid)):
        if _log_shows_done():
            return _finish_job(session_state, int(pid), 0, output_dir)
        return "running"

    code = 0 if _log_shows_done() else 1
    return _finish_job(session_state, int(pid), code, output_dir)


def pipeline_elapsed(session_state) -> int:
    return int(time.time() - session_state.get("pipeline_started", time.time()))


def pipeline_error_hint() -> str:
    return _log_tail(1500)


__all__ = [
    "JobState",
    "cancel_pipeline_job",
    "check_pipeline_job",
    "parse_pipeline_progress",
    "pipeline_elapsed",
    "pipeline_error_hint",
    "start_pipeline_job",
    "sync_pipeline_session",
    "update_job_progress",
]

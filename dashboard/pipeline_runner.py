"""Run video pipeline in a subprocess so Streamlit stays connected."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from dashboard.debug_log import dbg

ROOT = Path(__file__).resolve().parents[1]
CHUNK_BYTES = 8 * 1024 * 1024
_JOB_META = ROOT / "data" / "pipeline_job.json"
_LOG_PATH = ROOT / "data" / "pipeline_last_run.log"

# Keep Popen handles server-side; session_state only stores the PID (int).
_ACTIVE_JOBS: dict[int, subprocess.Popen] = {}

JobState = Literal["idle", "running", "success", "failed"]


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


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if sys.platform == "win32":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def _log_shows_done() -> bool:
    if not _LOG_PATH.exists():
        return False
    try:
        tail = _LOG_PATH.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        return False
    return "Done" in tail and "frames" in tail


def start_pipeline_job(video_path: Path, output_name: str) -> int:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "run_video.py"),
        "--input",
        str(video_path),
        "--output",
        output_name,
    ]
    dbg(
        "pipeline_runner:start",
        "subprocess_spawn",
        {"video": str(video_path), "output": output_name},
        hypothesis_id="H2",
        run_id="post-fix",
    )
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
        }
    )
    return proc.pid


def _finish_job(session_state, pid: int, code: int, output_dir: Path) -> JobState:
    _ACTIVE_JOBS.pop(pid, None)
    session_state.pop("pipeline_pid", None)
    session_state.pipeline_busy = False

    meta = _read_job_meta()
    out_name = meta.get("output") or session_state.get("pipeline_out", "dashboard_test.mp4")
    dbg("pipeline_runner:poll", "finished", {"code": code, "pid": pid}, hypothesis_id="H2", run_id="post-fix")

    if code != 0:
        session_state.pipeline_error = True
        meta["status"] = "failed"
        meta["exit_code"] = code
        _write_job_meta(meta)
        return "failed"

    session_state.pipeline_done_out = out_name
    meta["status"] = "success"
    meta["exit_code"] = 0
    _write_job_meta(meta)
    return "success"


def check_pipeline_job(session_state, output_dir: Path) -> JobState:
    """Poll subprocess once. Use with render_pipeline_monitor fragment."""
    pid = session_state.get("pipeline_pid")
    if not pid:
        return "idle"

    proc = _ACTIVE_JOBS.get(int(pid))
    if proc is not None:
        code = proc.poll()
        if code is None:
            return "running"
        return _finish_job(session_state, int(pid), code, output_dir)

    # Popen handle lost after rerun — fall back to PID + log file.
    if pid_alive(int(pid)):
        if _log_shows_done():
            return _finish_job(session_state, int(pid), 0, output_dir)
        return "running"

    code = 0 if _log_shows_done() else 1
    return _finish_job(session_state, int(pid), code, output_dir)


def pipeline_elapsed(session_state) -> int:
    return int(time.time() - session_state.get("pipeline_started", time.time()))


def pipeline_error_hint() -> str:
    if _LOG_PATH.exists():
        return _LOG_PATH.read_text(encoding="utf-8", errors="replace")[-1500:]
    return ""

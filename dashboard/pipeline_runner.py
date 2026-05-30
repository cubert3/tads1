"""Run video pipeline in a subprocess so Streamlit stays connected."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Literal

from dashboard.debug_log import dbg, dbg_exc

ROOT = Path(__file__).resolve().parents[1]
CHUNK_BYTES = 8 * 1024 * 1024

JobState = Literal["idle", "running", "success", "failed"]


def save_upload_chunked(uploaded_file, dest: Path) -> int:
    """Stream upload to disk; returns bytes written."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with dest.open("wb") as out:
        uploaded_file.seek(0)
        while True:
            chunk = uploaded_file.read(CHUNK_BYTES)
            if not chunk:
                break
            out.write(chunk)
            total += len(chunk)
    dbg("pipeline_runner:save", "upload_saved", {"path": str(dest), "bytes": total}, hypothesis_id="H1", run_id="post-fix")
    return total


def start_pipeline_job(video_path: Path, output_name: str) -> subprocess.Popen:
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
    log_path = ROOT / "data" / "pipeline_last_run.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_handle = log_path.open("w", encoding="utf-8")
    return subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def check_pipeline_job(session_state, output_dir: Path) -> JobState:
    """
    Poll subprocess once. Does NOT call st.rerun — use with @st.fragment(run_every=...).
    """
    proc = session_state.get("pipeline_proc")
    if proc is None:
        return "idle"

    code = proc.poll()
    if code is None:
        return "running"

    out_name = session_state.get("pipeline_out", "dashboard_test.mp4")
    session_state.pop("pipeline_proc", None)
    session_state.pipeline_busy = False

    dbg("pipeline_runner:poll", "finished", {"code": code}, hypothesis_id="H2", run_id="post-fix")

    if code != 0:
        session_state.pipeline_error = True
        return "failed"

    session_state.pipeline_done_out = out_name
    return "success"


def pipeline_elapsed(session_state) -> int:
    return int(time.time() - session_state.get("pipeline_started", time.time()))


def pipeline_error_hint() -> str:
    log_file = ROOT / "data" / "pipeline_last_run.log"
    if log_file.exists():
        return log_file.read_text(encoding="utf-8", errors="replace")[-1500:]
    return ""

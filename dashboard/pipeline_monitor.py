"""Stable Streamlit fragment for background pipeline polling."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard.pipeline_runner import (
    check_pipeline_job,
    parse_pipeline_progress,
    pipeline_elapsed,
    pipeline_error_hint,
)


@st.fragment(run_every=2)
def render_pipeline_monitor(output_dir: Path) -> None:
    if not st.session_state.get("pipeline_pid"):
        return

    state = check_pipeline_job(st.session_state, output_dir)
    if state == "running":
        elapsed = pipeline_elapsed(st.session_state)
        progress = parse_pipeline_progress()
        label = f"Processing in background — {elapsed}s elapsed. Keep this tab open."
        st.status(label, state="running")
        if progress:
            st.progress(progress["pct"], text=f"Frame {progress['done']} / {progress['total']}")
            if progress["fps"] > 0:
                remaining = max(0, progress["total"] - progress["done"])
                eta = int(remaining / progress["fps"])
                st.caption(f"~{progress['fps']:.1f} FPS · about {eta}s remaining")
    elif state == "success":
        import time

        out_name = st.session_state.get("pipeline_done_out", "dashboard_test.mp4")
        out_path = output_dir / out_name
        st.session_state.pipeline_finished_at = time.time()
        st.session_state.show_collision_hero = True
        if out_path.exists() and out_path.stat().st_size > 10_000:
            st.session_state["lab_annotated"] = str(out_path)
            st.session_state["lab_source_path"] = st.session_state.get("pipeline_source_video", "")
        if not st.session_state.get("_pipeline_success_rerun"):
            st.session_state._pipeline_success_rerun = True
            st.rerun()
    elif state == "failed":
        st.error("Pipeline failed — see Detection result above.")
        if not st.session_state.get("_pipeline_failed_rerun"):
            st.session_state._pipeline_failed_rerun = True
            st.rerun()

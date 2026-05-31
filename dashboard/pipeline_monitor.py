"""Stable Streamlit fragment for background pipeline polling."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard.debug_log import dbg
from dashboard.pipeline_runner import (
    check_pipeline_job,
    pipeline_elapsed,
    pipeline_error_hint,
)


@st.fragment(run_every=2)
def render_pipeline_monitor(output_dir: Path) -> None:
    """Poll an active pipeline job. Stable module-level fragment (not nested in app.py)."""
    if not st.session_state.get("pipeline_pid"):
        return

    state = check_pipeline_job(st.session_state, output_dir)
    dbg(
        "pipeline_monitor:poll",
        "tick",
        {"state": state, "pid": st.session_state.get("pipeline_pid")},
        hypothesis_id="H16",
        run_id="post-fix",
    )

    if state == "running":
        st.status(
            f"Processing in background — {pipeline_elapsed(st.session_state)}s. Keep this tab open.",
            state="running",
        )
    elif state == "success":
        out_name = st.session_state.get("pipeline_done_out", "dashboard_test.mp4")
        st.success("Processing complete.")
        out_path = output_dir / out_name
        if out_path.exists() and out_path.stat().st_size > 10_000:
            st.caption(f"Output: `{out_path}` ({out_path.stat().st_size // (1024 * 1024)} MB)")
            with st.expander("Play annotated video"):
                st.video(str(out_path))
        else:
            st.info("Check output/annotated/ and Incident registry.")
    elif state == "failed":
        st.error(f"Pipeline failed. {pipeline_error_hint()}")

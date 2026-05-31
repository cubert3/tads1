"""Large collision alert panel after a video run."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable

import streamlit as st

from core.config import Settings
from dashboard.utils import format_video_time, normalize_dispatch_status, pick_primary_incident


def render_collision_hero(
    *,
    incident: dict,
    incidents_dir: Path,
    settings: Settings,
    total_in_run: int,
    confirm_fn: Callable[[str], None],
    dismiss_fn: Callable[[str], None],
) -> None:
    sev = incident.get("severity", "collision").upper()
    t_sec = float(incident.get("timestamp_sec", 0))
    timecode = format_video_time(t_sec)
    score = float(incident.get("score", 0))

    st.markdown(
        f"""
        <div style="
            background: linear-gradient(135deg, #2a1518 0%, #14171b 100%);
            border: 2px solid #b85c50;
            border-radius: 4px;
            padding: 1.5rem 1.75rem;
            margin-bottom: 1.25rem;
        ">
            <p style="margin:0;font-size:0.6875rem;letter-spacing:0.14em;text-transform:uppercase;color:#b85c50;">
                Collision detected
            </p>
            <p style="margin:0.35rem 0 0;font-size:2rem;font-weight:600;color:#e4e7eb;line-height:1.2;">
                {sev} @ {timecode}
            </p>
            <p style="margin:0.5rem 0 0;font-size:0.875rem;color:#9aa3ad;">
                Confidence score {score:.2f} · {total_in_run} event(s) logged to database
                · dispatch {normalize_dispatch_status(incident.get("dispatch_status"))}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns([1.2, 1, 1])
    with c1:
        kf = incidents_dir / f"{incident['id']}_keyframe.jpg"
        clip = incidents_dir / f"{incident['id']}.mp4"
        if kf.exists():
            st.image(str(kf), caption=f"Evidence @ {timecode}", width="stretch")
        elif clip.exists():
            st.video(str(clip))
        else:
            st.warning("Evidence clip encoding — check Incident registry shortly.")

    with c2:
        st.metric("Video timestamp", timecode)
        st.metric("Severity", sev)
        st.metric("Event type", incident.get("event_type", "—"))
        st.caption(f"Incident ID: `{incident['id']}`")
        st.caption(f"Saved: {datetime.fromtimestamp(incident.get('created_at', 0)).strftime('%H:%M:%S')}")

    with c3:
        st.markdown("**Emergency routing (demo)**")
        st.write(f"Police: {settings.road_sos.dispatch.police_number or '—'}")
        st.write(f"Ambulance: {settings.road_sos.dispatch.ambulance_number or '—'}")
        if st.button("CONFIRM & DISPATCH (SMS/Call demo)", type="primary", width="stretch", key=f"hero_dispatch_{incident['id']}"):
            confirm_fn(incident["id"])
            st.success("Dispatched — logged to database and dispatch log.")
            st.rerun()
        if st.button("Dismiss false alarm", width="stretch", key=f"hero_dismiss_{incident['id']}"):
            dismiss_fn(incident["id"])
            st.rerun()


def load_run_primary(
    store,
    pipeline_started: float | None,
    source_video: str | None,
) -> tuple[dict | None, list[dict]]:
    import asyncio

    from dashboard.run_summary import read_run_summary

    summary = read_run_summary()
    if summary and summary.get("finished_at"):
        since = float(summary["finished_at"]) - 300
        recent = asyncio.run(store.list_since(since, limit=800))
        if source_video:
            src_name = Path(source_video).name
            recent = [
                r
                for r in recent
                if src_name in str(r.get("source_video", "")) or source_video in str(r.get("source_video", ""))
            ]
        pid = summary.get("primary_incident_id")
        if pid:
            row = asyncio.run(store.get(pid))
            if row:
                return row, recent
        primary = pick_primary_incident(recent)
        return primary, recent

    since = (pipeline_started or 0) - 5
    recent = asyncio.run(store.list_since(since, limit=800))
    if source_video:
        src_name = Path(source_video).name
        recent = [
            r
            for r in recent
            if src_name in str(r.get("source_video", "")) or source_video in str(r.get("source_video", ""))
        ]
    primary = pick_primary_incident(recent)
    return primary, recent


def render_lab_detection_result(
    *,
    store,
    settings: Settings,
    incidents_dir: Path,
    pipeline_busy: bool,
    confirm_fn: Callable[[str], None],
    dismiss_fn: Callable[[str], None],
) -> None:
    """Large verdict block at top of Upload & test lab."""
    from dashboard.run_summary import read_run_summary

    if pipeline_busy:
        from dashboard.pipeline_runner import (
            cancel_pipeline_job,
            parse_pipeline_progress,
            pipeline_elapsed,
        )

        with st.container(border=True):
            st.markdown("## Detection result")
            st.markdown("### Analyzing video…")
            elapsed = pipeline_elapsed(st.session_state)
            progress = parse_pipeline_progress()
            if progress:
                st.progress(progress["pct"], text=f"Frame {progress['done']} / {progress['total']}")
                st.caption(f"{elapsed}s elapsed · ~{progress['fps']:.1f} FPS on CPU")
            else:
                st.caption(f"{elapsed}s elapsed — starting detector (first progress update in ~30s)…")
            st.info(
                "Stay on this tab. Short clips (~30s) often take 4–8 minutes on CPU; "
                "longer or busy videos can take 10–20 minutes."
            )
            if st.button("Cancel processing", type="secondary", key="lab_cancel_pipeline"):
                cancel_pipeline_job(st.session_state)
                st.rerun()
        return

    if st.session_state.get("pipeline_error"):
        from dashboard.pipeline_runner import pipeline_error_hint as peh
        from dashboard.run_summary import read_run_summary

        with st.container(border=True):
            st.markdown("## Detection result")
            st.markdown("### Processing failed or was cancelled")
            hint = peh()
            if "write_text() got an unexpected keyword argument" in hint:
                st.warning(
                    "The video was analyzed but saving the summary crashed (now fixed). "
                    "Click **Process selected sample** again, or check **Incidents** for events from the last run."
                )
            st.code(hint[-800:] or "No log")
            if st.button("Clear error and try again", key="lab_clear_pipeline_error"):
                st.session_state.pop("pipeline_error", None)
                st.session_state.pop("pipeline_done_out", None)
                st.rerun()
        meta_video = st.session_state.get("pipeline_source_video")
        primary, run_events = load_run_primary(store, st.session_state.get("pipeline_started"), meta_video)
        if primary or run_events:
            st.session_state.pipeline_done_out = st.session_state.get("pipeline_out", "lab_recovered.mp4")
            st.caption("Events from the last run are shown below (summary file may be missing).")
        else:
            return

    if not st.session_state.get("pipeline_done_out"):
        return

    summary = read_run_summary() or {}
    primary, run_events = load_run_primary(
        store,
        st.session_state.get("pipeline_started"),
        st.session_state.get("pipeline_source_video"),
    )
    count = int(summary.get("incident_count", len(run_events)))

    with st.container(border=True):
        st.markdown("## Detection result")

        if primary and count > 0:
            sev = (primary.get("severity") or "").lower()
            timecode = format_video_time(float(primary.get("timestamp_sec", 0)))
            is_accident = sev in ("severe", "collision") or primary.get("event_type") == "collision"

            if is_accident:
                st.error(f"### ACCIDENT DETECTED at {timecode}")
                st.caption("The system flagged a collision in this video. Review evidence below, then confirm dispatch or dismiss.")
            else:
                st.warning(f"### NEAR-MISS DETECTED at {timecode}")
                st.caption("No severe collision class — closest event is a near-miss. You can still confirm if you treat it as an incident.")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Time in video", timecode)
            m2.metric("Severity", sev.upper())
            m3.metric("Confidence", f"{float(primary.get('score', 0)):.2f}")
            m4.metric("Events logged", str(count))

            render_collision_hero(
                incident=primary,
                incidents_dir=incidents_dir,
                settings=settings,
                total_in_run=count,
                confirm_fn=confirm_fn,
                dismiss_fn=dismiss_fn,
            )
        elif count > 0:
            st.warning(f"### {count} event(s) logged — open Incident registry to review")
            st.caption("Could not pick a single primary event. Lower **Confirm frames** in tuning if you see too many false positives.")
        else:
            st.success("### NO ACCIDENT DETECTED")
            st.write(
                "This run did not store any collision or near-miss in the database. "
                "The video may have no crash in frame, or thresholds may be too strict."
            )
            st.caption(f"Source: {summary.get('source_video', '—')}")

    st.markdown("---")

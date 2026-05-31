from __future__ import annotations

import asyncio
import sys
import time as _time
from datetime import datetime
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import get_settings
from dashboard.collision_hero import load_run_primary, render_collision_hero, render_lab_detection_result
from dashboard.pipeline_monitor import render_pipeline_monitor
import dashboard.pipeline_runner as pipeline_runner
from dashboard.screens import (
    render_analytics_screen,
    render_cameras_screen,
    render_dispatch_screen,
    render_incidents_screen,
    render_live_operations,
    render_test_lab,
)
from dashboard.theme import inject_theme, render_topbar, sidebar_block
from storage.incident_store import IncidentStore
from storage.runtime_settings import human_confirm_enabled, set_human_confirm_enabled
from storage.seed_demo import seed_demo_sync

st.set_page_config(
    page_title="Road SOS",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

settings = get_settings()
store = IncidentStore(settings.resolve_path(settings.paths.database_path))
incidents_dir = settings.resolve_path(settings.paths.incidents_dir)
output_dir = settings.resolve_path(settings.paths.output_dir)
uploads_dir = settings.resolve_path("data/uploads")
samples_dir = settings.resolve_path(settings.paths.samples_dir)
road = settings.road_sos
API_BASE = st.session_state.get("api_base", "http://127.0.0.1:8000")

if "human_confirm" not in st.session_state:
    st.session_state.human_confirm = human_confirm_enabled(road.human_confirm_enabled)

if "demo_seeded" not in st.session_state:
    existing = asyncio.run(store.list_all())
    if not existing:
        seed_demo_sync(force=False)
    st.session_state.demo_seeded = True


async def load_incidents(severity=None, state=None):
    return await store.list_all(severity=severity, state=state)


def _confirm_incident(incident_id: str) -> None:
    from core.processor import AccidentDetectionProcessor

    proc = AccidentDetectionProcessor(settings=settings)
    asyncio.run(proc.approve_and_dispatch(incident_id))


def _dismiss_incident(incident_id: str) -> None:
    from core.processor import AccidentDetectionProcessor

    proc = AccidentDetectionProcessor(settings=settings)
    asyncio.run(proc.dismiss_incident(incident_id))


def _queue_pipeline_job(video_path: Path, out_name: str) -> None:
    if not video_path.exists():
        st.error(f"File not found: {video_path}")
        return
    if st.session_state.get("pipeline_pid") is not None:
        st.warning("A job is already running.")
        return
    st.session_state.pipeline_busy = True
    st.session_state.pipeline_pid = pipeline_runner.start_pipeline_job(video_path, out_name)
    st.session_state.pipeline_out = out_name
    st.session_state.pipeline_started = _time.time()
    st.session_state.pipeline_source_video = str(video_path)
    st.session_state.pop("pipeline_error", None)
    st.session_state.pop("pipeline_done_out", None)
    st.session_state.pop("show_collision_hero", None)
    st.session_state.pop("_pipeline_success_rerun", None)
    st.session_state.pop("_pipeline_failed_rerun", None)
    st.rerun()


def _sync_pipeline_from_disk() -> None:
    fn = getattr(pipeline_runner, "sync_pipeline_session", None)
    if fn is not None:
        fn(st.session_state, output_dir)


_sync_pipeline_from_disk()


# —— Sidebar ——
with st.sidebar:
    st.markdown('<p class="rsos-sidebar-label" style="margin-top:0;">Control plane</p>', unsafe_allow_html=True)
    role = st.selectbox("Role", ["Operator", "Administrator"], key="user_role")
    hc = st.toggle("Human confirm before dispatch", value=st.session_state.human_confirm)
    if hc != st.session_state.human_confirm:
        st.session_state.human_confirm = hc
        set_human_confirm_enabled(hc)

    st.divider()
    if role == "Administrator":
        if st.button("Reload demo dataset"):
            seed_demo_sync(force=True)
            st.rerun()
        st.text_input("API base URL", value=API_BASE, key="api_base")

    sidebar_block("Post location", road.location.label, mono=f"{road.location.latitude:.5f}, {road.location.longitude:.5f}")
    sidebar_block("Police", road.dispatch.police_number or "Not set")
    sidebar_block("Ambulance", road.dispatch.ambulance_number or "Not set")

    st.divider()
    page = st.radio(
        "View",
        [
            "Live operations",
            "Upload & test lab",
            "Incidents",
            "Dispatch log",
            "Cameras & health",
            "Analytics",
        ],
        key="nav_page",
        label_visibility="collapsed",
    )

if st.session_state.get("pipeline_pid"):
    render_pipeline_monitor(output_dir)

pipeline_busy = bool(st.session_state.get("pipeline_pid"))
from storage.runtime_settings import get_camera_config

cam = get_camera_config()
conn = "degraded" if pipeline_busy else ("online" if cam.get("url") else "offline")

render_topbar(
    clock=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    camera_name=cam["name"],
    connection=conn,
    webhook_on=bool(settings.alerts.webhook_url),
)

page = st.session_state.get("nav_page", "Live operations")

if page != "Upload & test lab" and (
    st.session_state.get("show_collision_hero")
    or (st.session_state.get("pipeline_done_out") and not st.session_state.get("pipeline_pid"))
):
    primary, run_events = load_run_primary(
        store,
        st.session_state.get("pipeline_started"),
        st.session_state.get("pipeline_source_video"),
    )
    if primary:
        render_collision_hero(
            incident=primary,
            incidents_dir=incidents_dir,
            settings=settings,
            total_in_run=len(run_events),
            confirm_fn=_confirm_incident,
            dismiss_fn=_dismiss_incident,
        )
    elif st.session_state.get("pipeline_done_out"):
        st.warning(
            "Processing finished but no collision/near-miss was stored for this run. "
            "Try lowering **Confirm frames** or **IoU threshold** in Upload & test lab."
        )

pending = asyncio.run(load_incidents(state="pending_review"))
confirmed = asyncio.run(load_incidents(state="confirmed"))
zones = asyncio.run(store.list_cooldown_zones())
dispatch_logs = asyncio.run(store.list_dispatch_log(limit=50))
last_dispatch_at = dispatch_logs[0]["created_at"] if dispatch_logs else None

if page == "Live operations":
    render_live_operations(
        store=store,
        settings=settings,
        incidents_dir=incidents_dir,
        output_dir=output_dir,
        pending=pending,
        confirmed=confirmed,
        cooldown_count=len(zones),
        last_dispatch_at=last_dispatch_at,
        pipeline_busy=pipeline_busy,
        confirm_fn=_confirm_incident,
        dismiss_fn=_dismiss_incident,
    )

elif page == "Upload & test lab":
    render_lab_detection_result(
        store=store,
        settings=settings,
        incidents_dir=incidents_dir,
        pipeline_busy=pipeline_busy,
        confirm_fn=_confirm_incident,
        dismiss_fn=_dismiss_incident,
    )
    render_test_lab(
        settings=settings,
        incidents_dir=incidents_dir,
        output_dir=output_dir,
        uploads_dir=uploads_dir,
        samples_dir=samples_dir,
        queue_job=_queue_pipeline_job,
        api_base=st.session_state.get("api_base", API_BASE),
    )

elif page == "Incidents":
    render_incidents_screen(
        store=store,
        incidents_dir=incidents_dir,
        output_dir=output_dir,
        load_incidents_fn=load_incidents,
        confirm_fn=_confirm_incident,
        dismiss_fn=_dismiss_incident,
    )

elif page == "Dispatch log":
    render_dispatch_screen(dispatch_logs, incidents_dir, road)

elif page == "Cameras & health":
    render_cameras_screen(settings, pipeline_busy)

elif page == "Analytics":
    summary = asyncio.run(store.analytics_summary())
    timeline = asyncio.run(store.analytics_timeline())
    pins = asyncio.run(store.map_pins())
    render_analytics_screen(summary, timeline, pins)
    from dashboard.theme import plot_cooldown_chart, render_section

    render_section("Cooldown zones")
    if zones:
        plot_cooldown_chart(zones)
    else:
        st.caption("No active cooldown zones.")

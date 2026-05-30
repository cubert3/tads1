from __future__ import annotations

import asyncio
import sys
import tempfile
import time as _time
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.processor import AccidentDetectionProcessor
from dashboard.theme import (
    SEVERITY_CLASS,
    inject_theme,
    plot_cooldown_chart,
    render_analytics_bars,
    render_badge,
    render_empty,
    render_html_table,
    render_meta_grid,
    render_panel_header,
    render_section,
    render_stat_grid,
    render_topbar,
    sidebar_block,
)
from storage.incident_store import IncidentStore
from storage.runtime_settings import human_confirm_enabled, set_human_confirm_enabled
from storage.seed_demo import seed_demo_sync
from dashboard.debug_log import dbg, dbg_exc
from dashboard.pipeline_runner import (
    check_pipeline_job,
    pipeline_elapsed,
    pipeline_error_hint,
    save_upload_chunked,
    start_pipeline_job,
)

dbg("app.py:module", "dashboard_loaded", {}, hypothesis_id="H6", run_id="post-fix")

st.set_page_config(
    page_title="Road SOS",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded",
)

inject_theme()

if "dbg_run" not in st.session_state:
    st.session_state.dbg_run = 0
st.session_state.dbg_run += 1
dbg(
    "app.py:startup",
    "script_rerun",
    {"run": st.session_state.dbg_run, "processing": st.session_state.get("pipeline_busy", False)},
    hypothesis_id="H4",
)

settings = get_settings()
store = IncidentStore(settings.resolve_path(settings.paths.database_path))
incidents_dir = settings.resolve_path(settings.paths.incidents_dir)
output_dir = settings.resolve_path(settings.paths.output_dir)
road = settings.road_sos

if "human_confirm" not in st.session_state:
    st.session_state.human_confirm = human_confirm_enabled(road.human_confirm_enabled)

if "demo_seeded" not in st.session_state:
    try:
        existing = asyncio.run(store.list_all())
        if not existing:
            seed_demo_sync(force=False)
        st.session_state.demo_seeded = True
        dbg("app.py:seed", "demo_seed_done", {"had_existing": bool(existing)}, hypothesis_id="H4")
    except Exception as exc:
        dbg_exc("app.py:seed", exc, hypothesis_id="H3")
        raise


async def load_incidents(severity=None, state=None):
    return await store.list_all(severity=severity, state=state)


async def load_dispatch():
    return await store.list_dispatch_log()


async def load_cooldown():
    return await store.list_cooldown_zones()


async def load_analytics():
    return await store.analytics_summary()


def _severity_tone(sev: str) -> str:
    if sev in ("severe", "collision"):
        return "critical"
    if sev in ("near_miss", "pending_review"):
        return "warning"
    if sev == "confirmed":
        return "ok"
    return ""


def _confirm_incident(incident_id: str) -> None:
    proc = AccidentDetectionProcessor(settings=settings)
    asyncio.run(proc.approve_and_dispatch(incident_id))


def _dismiss_incident(incident_id: str) -> None:
    proc = AccidentDetectionProcessor(settings=settings)
    asyncio.run(proc.dismiss_incident(incident_id))


def _esc_path(s: str) -> str:
    import html

    return html.escape(s)


# —— Sidebar: operational configuration ——
with st.sidebar:
    st.markdown(
        '<p class="rsos-sidebar-label" style="margin-top:0;">Control plane</p>',
        unsafe_allow_html=True,
    )
    hc = st.toggle(
        "Human confirm before dispatch",
        value=st.session_state.human_confirm,
        help="Incidents require operator approval before emergency routing.",
    )
    if hc != st.session_state.human_confirm:
        st.session_state.human_confirm = hc
        set_human_confirm_enabled(hc)

    st.divider()

    if st.button("Reload demo dataset", help="Resets sample incidents, dispatch log, and cooldown zones"):
        seed_demo_sync(force=True)
        st.rerun()

    sidebar_block("Post location", road.location.label, mono=f"{road.location.latitude:.5f}, {road.location.longitude:.5f}")

    sidebar_block("Police line", road.dispatch.police_number or "Not configured")
    sidebar_block("Ambulance line", road.dispatch.ambulance_number or "Not configured")

    st.markdown('<p class="rsos-sidebar-label">Severity routing</p>', unsafe_allow_html=True)
    routing = road.severity_routing
    for label, key in [("Near miss", routing.near_miss), ("Collision", routing.collision), ("Severe", routing.severe)]:
        st.markdown(
            f'<div class="rsos-routing-line"><span class="rsos-routing-key">{label}</span>{key}</div>',
            unsafe_allow_html=True,
        )

    st.divider()
    page = st.radio(
        "View",
        ["Operations", "Analysis lab", "Incident registry", "Dispatch log", "Cooldown zones", "Statistics"],
        key="nav_page",
        label_visibility="collapsed",
    )
    dbg("app.py:sidebar", "page_selected", {"page": page}, hypothesis_id="H4", run_id="post-fix")

# —— Main shell ——
render_topbar("Emergency Response · Traffic Incident Detection")

# —— Operations ——
if page == "Operations":
    render_section(
        "Operations center",
        "Monitor active queue, confirm detections, and review the most recent verified incident.",
    )
    _t0 = _time.perf_counter()
    pending = asyncio.run(load_incidents(state="pending_review"))
    confirmed = asyncio.run(load_incidents(state="confirmed"))
    dbg(
        "app.py:tab_live",
        "tab_loaded",
        {"ms": round((_time.perf_counter() - _t0) * 1000), "pending": len(pending), "confirmed": len(confirmed)},
        hypothesis_id="H4",
    )

    render_stat_grid(
        [
            ("Pending review", str(len(pending)), "warning" if pending else ""),
            ("Confirmed", str(len(confirmed)), "ok" if confirmed else ""),
            ("Human gate", "ENABLED" if st.session_state.human_confirm else "BYPASS", ""),
            ("Plate OCR", "ACTIVE" if road.plate_detection_enabled else "OFF", ""),
        ]
    )

    if pending:
        render_section("Review queue", "Operator action required before dispatch.")
        for inc in pending[:5]:
            sev = inc.get("severity", "unknown")
            badge = render_badge(sev.upper(), sev)
            with st.container(border=True):
                render_panel_header(
                    f"Incident @ {inc['timestamp_sec']:.1f}s · score {inc['score']:.2f}",
                    badge,
                )
                render_meta_grid(
                    [
                        ("Identifier", inc["id"][:8] + "…"),
                        ("Event", inc.get("event_type", "—")),
                        ("Signals", ", ".join(inc.get("signals") or [])),
                    ]
                )
                c1, c2, c3 = st.columns([1, 1, 2])
                with c1:
                    if st.button("Confirm dispatch", key=f"live_ok_{inc['id']}", type="primary"):
                        _confirm_incident(inc["id"])
                        st.rerun()
                with c2:
                    if st.button("Dismiss", key=f"live_no_{inc['id']}"):
                        _dismiss_incident(inc["id"])
                        st.rerun()
                clip = incidents_dir / f"{inc['id']}.mp4"
                if clip.exists():
                    with c3:
                        st.video(str(clip))
                elif (incidents_dir / f"{inc['id']}.json").exists():
                    with c3:
                        st.caption("Demo record — evidence clip appears after live processing.")
    elif confirmed:
        render_section("Last verified incident")
        last = confirmed[0]
        badge = render_badge(last.get("state", "confirmed"), "confirmed")
        with st.container(border=True):
            render_panel_header(
                f"{last['severity'].upper()} · {last.get('event_type', '')} @ {last['timestamp_sec']:.1f}s",
                badge,
            )
            render_meta_grid(
                [
                    ("Dispatch", last.get("dispatch_status", "—")),
                    ("Source", Path(str(last.get("source_video", "—"))).name),
                ]
            )
            clip = incidents_dir / f"{last['id']}.mp4"
            if clip.exists():
                st.video(str(clip))
            if last.get("latitude") and last.get("longitude"):
                st.map({"lat": [last["latitude"]], "lon": [last["longitude"]]})
    else:
        render_empty("No active incidents. Submit footage in Analysis lab to begin detection.")

    st.markdown(
        '<p style="font-size:0.6875rem;color:#5f6872;margin-top:1rem;">'
        "Live ingest: <code style='font-family:IBM Plex Mono,monospace;'>"
        "scripts/run_live.py --camera 0</code> or <code>--rtsp &lt;url&gt;</code></p>",
        unsafe_allow_html=True,
    )

# —— Analysis lab ——
elif page == "Analysis lab":
    render_section(
        "Analysis lab",
        "Process recorded footage through the detection pipeline for validation and demonstration.",
    )

    st.caption(
        "No custom accident training required — pretrained YOLOv8 (vehicles) + rule-based collision logic. "
        "One-time setup: deps, yolov8n.pt, lap. See docs/SETUP_AND_TRAINING.md."
    )

    def _queue_pipeline_job(video_path: Path, out_name: str) -> None:
        if not video_path.exists():
            st.error(f"File not found: {video_path}")
            return
        if st.session_state.get("pipeline_proc") is not None:
            st.warning("A job is already running.")
            return
        st.session_state.pipeline_busy = True
        st.session_state.pipeline_proc = start_pipeline_job(video_path, out_name)
        st.session_state.pipeline_out = out_name
        st.session_state.pipeline_started = _time.time()
        st.session_state.pop("pipeline_error", None)
        st.session_state.pop("pipeline_done_out", None)
        dbg("app.py:tab_lab", "job_queued", {"path": str(video_path), "out": out_name}, hypothesis_id="H2", run_id="post-fix")

    @st.fragment(run_every=2)
    def _pipeline_monitor() -> None:
        state = check_pipeline_job(st.session_state, output_dir)
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
                st.video(str(out_path))
            else:
                st.info("Check output/annotated/ and Incident registry.")
        elif state == "failed":
            st.error(f"Pipeline failed. {pipeline_error_hint()}")

    _pipeline_monitor()

    uploads_dir = settings.resolve_path("data/uploads")
    uploads_dir.mkdir(parents=True, exist_ok=True)

    st.info("Recommended: use **Process sample from disk** below to avoid browser upload disconnects.")

    uploaded = st.file_uploader(
        "Source footage (optional)",
        type=["mp4", "avi", "mov", "mkv"],
        key="lab_upload",
    )
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Save upload to disk", disabled=uploaded is None):
            if uploaded is None:
                st.error("Select a file first.")
            elif uploaded.size and uploaded.size > 500 * 1024 * 1024:
                st.error("File exceeds 500 MB.")
            else:
                try:
                    dbg("app.py:tab_lab", "save_upload_click", {"size": uploaded.size}, hypothesis_id="H1", run_id="post-fix")
                    dest = uploads_dir / uploaded.name
                    save_upload_chunked(uploaded, dest)
                    st.session_state.upload_path = str(dest)
                    st.success(f"Saved ({uploaded.size // (1024 * 1024)} MB).")
                except Exception as exc:
                    dbg_exc("app.py:tab_lab", exc, hypothesis_id="H3", run_id="post-fix")
                    st.error(str(exc))
    with col_b:
        out_name_upload = st.text_input("Output label", value="dashboard_test.mp4", key="out_upload")
        if st.button("Execute saved upload", type="primary"):
            path_str = st.session_state.get("upload_path")
            if not path_str:
                st.error("Click **Save upload to disk** first.")
            else:
                _queue_pipeline_job(Path(path_str), out_name_upload)

    render_section("Local sample library", "Process from disk — most reliable.")
    samples = settings.resolve_path(settings.paths.samples_dir)
    sample_videos = sorted(samples.glob("*.mp4")) if samples.exists() else []
    if sample_videos:
        choice = st.selectbox("Sample file", [v.name for v in sample_videos], key="sample_pick")
        out_name_sample = st.text_input("Output label", value=f"annotated_{Path(choice).stem}.mp4", key="out_sample")
        if st.button("Process sample from disk", type="primary"):
            _queue_pipeline_job(samples / choice, out_name_sample)
    else:
        render_empty("Put .mp4 files in data/samples/ then use Process sample from disk.")


# —— Incident registry ——
elif page == "Incident registry":
    render_section("Incident registry", "Search, filter, and adjudicate stored detections.")

    f1, f2, f3 = st.columns([1, 1, 1])
    with f1:
        severity_filter = st.selectbox("Severity", ["All", "near_miss", "collision", "severe"], label_visibility="visible")
    with f2:
        state_filter = st.selectbox(
            "State",
            ["All", "pending_review", "confirmed", "dismissed"],
            label_visibility="visible",
        )
    with f3:
        st.markdown("<div style='height:1.75rem'></div>", unsafe_allow_html=True)

    sev = None if severity_filter == "All" else severity_filter
    state = None if state_filter == "All" else state_filter
    incidents = asyncio.run(load_incidents(severity=sev, state=state))

    render_stat_grid([("Matching records", str(len(incidents)), "")])

    if not incidents:
        render_empty("No records match the current filters.")
    else:
        for inc in incidents:
            state_val = inc.get("state", "unknown")
            sev = inc.get("severity", "unknown")
            badge = render_badge(f"{state_val.replace('_', ' ')}", state_val if state_val in SEVERITY_CLASS else sev)
            plates = inc.get("plate_numbers") or []
            title = f"{sev.upper()} · {inc.get('event_type', '')} · t={inc['timestamp_sec']:.1f}s"
            with st.expander(title, expanded=state_val == "pending_review"):
                st.markdown(badge, unsafe_allow_html=True)
                render_meta_grid(
                    [
                        ("ID", inc["id"]),
                        ("Dispatch", inc.get("dispatch_status", "—")),
                        ("Score", f"{inc.get('score', 0):.2f}"),
                        ("Signals", ", ".join(inc.get("signals") or [])),
                        ("Tracks", str(inc.get("track_ids") or "—")),
                        ("Plates", ", ".join(plates) if plates else "Not extracted"),
                        ("Source", Path(str(inc.get("source_video", "—"))).name),
                    ]
                )
                if inc.get("latitude"):
                    st.caption(f"{inc.get('location_label')} — {inc['latitude']}, {inc['longitude']}")
                    st.map({"lat": [inc["latitude"]], "lon": [inc["longitude"]]})

                if state_val == "pending_review":
                    b1, b2 = st.columns(2)
                    if b1.button("Confirm dispatch", key=f"c_{inc['id']}", type="primary"):
                        _confirm_incident(inc["id"])
                        st.rerun()
                    if b2.button("Dismiss", key=f"d_{inc['id']}"):
                        _dismiss_incident(inc["id"])
                        st.rerun()

                clip = incidents_dir / f"{inc['id']}.mp4"
                if clip.exists():
                    st.video(str(clip))
                kf = incidents_dir / f"{inc['id']}_keyframe.jpg"
                if kf.exists():
                    st.image(str(kf), caption="Reference frame")

    render_section("Annotated exports")
    if output_dir.exists() and list(output_dir.glob("*.mp4")):
        for v in sorted(output_dir.glob("*.mp4")):
            with st.expander(v.name):
                st.video(str(v))
    else:
        render_empty("No annotated exports generated yet.")


# —— Dispatch log ——
elif page == "Dispatch log":
    rt = road.severity_routing
    render_section(
        "Dispatch log",
        f"Routing policy — near miss: {rt.near_miss}, collision: {rt.collision}, severe: {rt.severe}",
    )
    _t0 = _time.perf_counter()
    logs = asyncio.run(load_dispatch())
    dbg("app.py:tab_dispatch", "tab_loaded", {"ms": round((_time.perf_counter() - _t0) * 1000)}, hypothesis_id="H4")
    if logs:
        render_html_table(
            logs,
            [
                ("created_at", "Time"),
                ("action", "Action"),
                ("channel", "Channel"),
                ("target", "Target"),
                ("severity", "Severity"),
                ("status", "Status"),
            ],
        )
    else:
        render_empty("No dispatch events recorded. Confirm an incident to initiate routing.")

# —— Cooldown zones ——
elif page == "Cooldown zones":
    render_section(
        "Cooldown zones",
        f"Duplicate suppression — {settings.collision.cooldown_seconds}s window, "
        f"{settings.collision.cooldown_distance_px}px spatial radius (image coordinates).",
    )
    zones = asyncio.run(load_cooldown())
    if zones:
        plot_cooldown_chart(zones)
        render_html_table(
            zones,
            [
                ("reason", "Reason"),
                ("x", "X"),
                ("y", "Y"),
                ("radius_px", "Radius"),
                ("expires_at", "Expires"),
            ],
        )
    else:
        render_empty("No cooldown zones in the current window.")

# —— Statistics ——
elif page == "Statistics":
    render_section("Operational statistics", "Aggregate incident classification for the active dataset.")
    summary = asyncio.run(load_analytics())
    pending_n = summary.get("pending_review", 0)
    by_sev = summary.get("by_severity") or {}

    render_stat_grid(
        [
            ("Pending review", str(pending_n), "warning" if pending_n else ""),
            ("Classifications", str(sum(by_sev.values())), ""),
            ("Categories", str(len(by_sev)), ""),
        ]
    )
    render_section("Distribution by severity")
    render_analytics_bars(by_sev)

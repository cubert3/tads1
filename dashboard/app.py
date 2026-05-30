from __future__ import annotations

import asyncio
import sys
import tempfile
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
from media.video_reader import VideoSource
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
road = settings.road_sos

if "human_confirm" not in st.session_state:
    st.session_state.human_confirm = human_confirm_enabled(road.human_confirm_enabled)

if "demo_seeded" not in st.session_state:
    existing = asyncio.run(store.list_all())
    if not existing:
        seed_demo_sync(force=False)
    st.session_state.demo_seeded = True


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

# —— Main shell ——
render_topbar("Emergency Response · Traffic Incident Detection")

tab_live, tab_lab, tab_incidents, tab_dispatch, tab_cooldown, tab_analytics = st.tabs(
    [
        "Operations",
        "Analysis lab",
        "Incident registry",
        "Dispatch log",
        "Cooldown zones",
        "Statistics",
    ]
)

# —— Operations ——
with tab_live:
    render_section(
        "Operations center",
        "Monitor active queue, confirm detections, and review the most recent verified incident.",
    )
    pending = asyncio.run(load_incidents(state="pending_review"))
    confirmed = asyncio.run(load_incidents(state="confirmed"))

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
with tab_lab:
    render_section(
        "Analysis lab",
        "Process recorded footage through the detection pipeline for validation and demonstration.",
    )

    st.caption(
        "No custom accident training required — pretrained YOLOv8 (vehicles) + rule-based collision logic. "
        "One-time setup: deps, yolov8n.pt, lap. See docs/SETUP_AND_TRAINING.md."
    )

    def _run_pipeline(video_path: Path, source_label: str, out_name: str) -> None:
        if not video_path.exists():
            st.error(f"File not found: {video_path}")
            return
        status = st.status("Processing video", expanded=True)
        try:
            status.write(f"Input: {source_label}")
            status.write("Loading YOLO + tracker — first run may take a minute…")
            processor = AccidentDetectionProcessor(settings=settings)
            result = processor.process_source(VideoSource.from_file(video_path), output_name=out_name)
            for inc in result.incidents:
                inc.source_video = source_label
                asyncio.run(store.save(inc))
            status.update(label="Complete", state="complete")
            render_stat_grid(
                [
                    ("Frames", str(result.frames_processed), ""),
                    ("Throughput", f"{result.fps_avg:.1f} FPS", ""),
                    ("Incidents", str(len(result.incidents)), "critical" if result.incidents else ""),
                ]
            )
            if result.annotated_path and result.annotated_path.exists():
                st.video(str(result.annotated_path))
            if not result.incidents:
                st.warning("No incidents confirmed — tune config/settings.yaml or try another clip.")
        except Exception as exc:
            status.update(label="Failed", state="error")
            st.error(f"Processing failed: {exc}")

    with st.form("pipeline_form", clear_on_submit=False):
        uploaded = st.file_uploader(
            "Source footage",
            type=["mp4", "avi", "mov", "mkv"],
            help="Select a file, then click Execute pipeline in this form.",
        )
        out_name = st.text_input("Output label", value="dashboard_test.mp4")
        submitted = st.form_submit_button("Execute pipeline", type="primary")

    if submitted:
        if uploaded is None:
            st.error("No file selected. Pick a video above, then click Execute pipeline.")
        else:
            tmp_path = Path(tempfile.gettempdir()) / f"tads_{uploaded.name}"
            tmp_path.write_bytes(uploaded.getvalue())
            _run_pipeline(tmp_path, uploaded.name, out_name)

    render_section("Local sample library", "Process from disk — reliable if browser upload fails.")
    samples = settings.resolve_path(settings.paths.samples_dir)
    sample_videos = sorted(samples.glob("*.mp4")) if samples.exists() else []
    if sample_videos:
        choice = st.selectbox("Sample file", [v.name for v in sample_videos], key="sample_pick")
        if st.button("Process sample from disk", type="primary"):
            _run_pipeline(samples / choice, choice, f"annotated_{Path(choice).stem}.mp4")
    else:
        render_empty("Put .mp4 files in data/samples/ then use Process sample from disk.")


# —— Incident registry ——
with tab_incidents:
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
with tab_dispatch:
    rt = road.severity_routing
    render_section(
        "Dispatch log",
        f"Routing policy — near miss: {rt.near_miss}, collision: {rt.collision}, severe: {rt.severe}",
    )
    logs = asyncio.run(load_dispatch())
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
with tab_cooldown:
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
with tab_analytics:
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

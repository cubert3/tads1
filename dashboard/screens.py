"""Road SOS dashboard screens (6-tab spec)."""

from __future__ import annotations

import asyncio
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

import streamlit as st

from core.config import Settings
from core.incident_manager import IncidentRecord, IncidentState
from dashboard.api_client import api_reachable, job_status, start_process, upload_video
from dashboard.live_preview import render_live_preview
from dashboard.theme import (
    plot_cooldown_chart,
    render_analytics_bars,
    render_badge,
    render_empty,
    render_html_table,
    render_meta_grid,
    render_panel_header,
    render_section,
    render_stat_grid,
    render_status_strip,
)
from dashboard.utils import (
    find_preview_image,
    format_video_time,
    normalize_dispatch_status,
    ops_status,
    parse_pipeline_fps,
)
from media.dispatch import DispatchService
from storage.incident_store import IncidentStore
from storage.runtime_settings import get_camera_config, get_detection_tuning, set_detection_tuning


async def trigger_test_dispatch(store: IncidentStore, settings: Settings) -> list:
    loc = settings.road_sos.location
    record = IncidentRecord(
        id=f"test-sos-{uuid.uuid4().hex[:8]}",
        state=IncidentState.CONFIRMED,
        event_type="collision",
        severity="severe",
        score=0.99,
        signals=["demo", "manual_sos"],
        track_ids=(1, 2),
        location=(400.0, 300.0),
        frame_index=0,
        timestamp_sec=time.time(),
        confirmed_at=time.time(),
        dispatch_status="called",
        latitude=loc.latitude,
        longitude=loc.longitude,
        location_label=loc.label,
        source_video="demo_sos_trigger",
        human_reviewed=True,
    )
    svc = DispatchService(settings.road_sos)
    return await svc.execute(
        record,
        settings.alerts.webhook_url,
        on_persist=store.save_dispatch_entries,
    )


def render_live_operations(
    *,
    store: IncidentStore,
    settings: Settings,
    incidents_dir: Path,
    output_dir: Path,
    pending: list,
    confirmed: list,
    cooldown_count: int,
    last_dispatch_at: float | None,
    pipeline_busy: bool,
    confirm_fn: Callable[[str], None],
    dismiss_fn: Callable[[str], None],
) -> None:
    active = ops_status(len(pending), cooldown_count, last_dispatch_at, pipeline_busy)
    render_status_strip(active)

    col_v, col_a = st.columns([1.2, 1])
    with col_v:
        render_section("Live preview", "ESP / RTSP snapshot or last processed frame (refreshes every 3s).")
        cam = get_camera_config()
        render_live_preview(incidents_dir, output_dir, rtsp_url=cam.get("url") or None)

    with col_a:
        render_section("Last alert")
        latest = pending[0] if pending else (confirmed[0] if confirmed else None)
        if latest:
            sev = latest.get("severity", "unknown")
            badge = render_badge(sev.upper(), sev)
            render_panel_header(
                f"{sev.upper()} · score {latest.get('score', 0):.2f} · t={latest['timestamp_sec']:.1f}s",
                badge,
            )
            render_meta_grid(
                [
                    ("Time", datetime.fromtimestamp(latest.get("created_at", time.time())).strftime("%H:%M:%S")),
                    ("Dispatch", normalize_dispatch_status(latest.get("dispatch_status"))),
                    ("Signals", ", ".join(latest.get("signals") or [])),
                ]
            )
            clip = incidents_dir / f"{latest['id']}.mp4"
            if clip.exists():
                st.video(str(clip))
            elif pending:
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Confirm dispatch", key="hero_confirm", type="primary"):
                        confirm_fn(latest["id"])
                        st.rerun()
                with c2:
                    if st.button("Dismiss", key="hero_dismiss"):
                        dismiss_fn(latest["id"])
                        st.rerun()
        else:
            render_empty("No alerts yet. Process a sample in Upload & test lab.")

    st.markdown('<div class="rsos-sos-btn">', unsafe_allow_html=True)
    if st.button("TRIGGER TEST DISPATCH (DEMO SOS)", type="primary", width="stretch"):
        asyncio.run(trigger_test_dispatch(store, settings))
        st.success(
            f"Test dispatch logged — police {settings.road_sos.dispatch.police_number or 'N/A'}, "
            f"ambulance {settings.road_sos.dispatch.ambulance_number or 'N/A'}"
        )
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    if pending:
        render_section("Review queue", f"{len(pending)} pending — showing first 5")
        for inc in pending[:5]:
            with st.expander(f"{inc['severity']} @ {inc['timestamp_sec']:.1f}s", expanded=False):
                if st.button("Confirm", key=f"op_c_{inc['id']}"):
                    confirm_fn(inc["id"])
                    st.rerun()
                if st.button("Dismiss", key=f"op_d_{inc['id']}"):
                    dismiss_fn(inc["id"])
                    st.rerun()


def render_test_lab(
    *,
    settings: Settings,
    incidents_dir: Path,
    output_dir: Path,
    uploads_dir: Path,
    samples_dir: Path,
    queue_job: Callable[[Path, str], None],
    api_base: str,
) -> None:
    tuning = get_detection_tuning(settings)
    render_section("Detection tuning", "Applied on the next pipeline run.")
    c1, c2, c3 = st.columns(3)
    with c1:
        prox = st.slider("Near-miss proximity (px)", 40, 160, int(tuning["proximity_px"]))
    with c2:
        confirm = st.slider("Confirm frames", 1, 8, int(tuning["confirm_frames"]))
    with c3:
        iou = st.slider("Collision IoU threshold", 0.1, 0.6, float(tuning["collision_iou_threshold"]), 0.05)
    if st.button("Save tuning for next run"):
        set_detection_tuning(prox, confirm, iou)
        st.success("Thresholds saved.")

    api_ok = api_reachable(api_base)
    st.caption(f"API {'online' if api_ok else 'offline'} at {api_base} — use disk pipeline if API is not running.")

    sample_videos = sorted(samples_dir.glob("*.mp4")) if samples_dir.exists() else []
    sample_names = [v.name for v in sample_videos]

    render_section("Source video", "Pick a sample — preview updates when you change the selection.")
    preview_path: Path | None = None
    if sample_names:
        if "sample_pick" not in st.session_state or st.session_state.sample_pick not in sample_names:
            st.session_state.sample_pick = sample_names[0]
        choice = st.selectbox("Sample file", sample_names, key="sample_pick")
        preview_path = samples_dir / choice
        st.session_state.lab_preview_path = str(preview_path)
        out_default = f"lab_{Path(choice).stem}.mp4"
    else:
        choice = None
        out_default = "lab_output.mp4"
        render_empty("Add .mp4 files under data/samples/.")

    with st.expander("Or use a custom file path"):
        custom = st.text_input(
            "Path on this PC",
            value=st.session_state.get("lab_custom_path", ""),
            key="lab_custom_path_input",
        )
        if custom.strip():
            custom_path = Path(custom.strip())
            if custom_path.exists():
                preview_path = custom_path
                st.session_state.lab_preview_path = str(preview_path)
            else:
                st.warning("File not found at that path.")

    use_last_run = st.checkbox(
        "Show source from last completed run (instead of selection above)",
        value=False,
        key="lab_use_last_run_source",
    )

    render_section("Upload video")
    uploaded = st.file_uploader("Drag and drop footage", type=["mp4", "avi", "mov", "mkv"], key="lab_upload")
    source_path: Path | None = None
    annotated_path: Path | None = None

    if uploaded is not None:
        if st.button("Save & process", type="primary"):
            suffix = Path(uploaded.name).suffix or ".mp4"
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                uploaded.seek(0)
                while True:
                    chunk = uploaded.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    tmp.write(chunk)
                source_path = Path(tmp.name)
            if api_ok:
                try:
                    meta = upload_video(source_path, api_base)
                    job = start_process(meta["video_id"], api_base)
                    st.session_state.api_job_id = job["job_id"]
                    st.session_state.api_source_path = str(source_path)
                    st.rerun()
                except Exception as exc:
                    st.warning(f"API upload failed ({exc}). Using local subprocess.")
                    queue_job(source_path, f"upload_{Path(uploaded.name).stem}.mp4")
            else:
                import shutil

                dest = uploads_dir / uploaded.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, dest)
                st.session_state.lab_preview_path = str(dest)
                queue_job(dest, f"upload_{Path(uploaded.name).stem}.mp4")

    job_id = st.session_state.get("api_job_id")
    if api_ok and job_id:

        @st.fragment(run_every=2)
        def _poll_api_job() -> None:
            try:
                js = job_status(job_id, api_base)
            except Exception as exc:
                st.error(str(exc))
                return
            st.progress(min(1.0, float(js.get("progress", 0))), text=f"Status: {js.get('status')}")
            if js.get("fps"):
                st.metric("Processing FPS", f"{js['fps']:.1f}")
            if js.get("status") == "completed":
                ap = js.get("annotated_path")
                if ap:
                    st.session_state.lab_annotated = ap
                st.session_state.pop("api_job_id", None)
                st.success(f"Done — {js.get('incidents', 0)} incidents")
            elif js.get("status") == "failed":
                st.error(js.get("error", "Job failed"))
                st.session_state.pop("api_job_id", None)

        _poll_api_job()

    annotated_path = None
    if st.session_state.get("lab_annotated"):
        annotated_path = Path(st.session_state["lab_annotated"])
    elif st.session_state.get("pipeline_done_out"):
        annotated_path = output_dir / st.session_state["pipeline_done_out"]

    render_section("Compare outputs")
    left, right = st.columns(2)
    with left:
        st.markdown("**Source**")
        display_path: Path | None = None
        if use_last_run:
            for key in ("lab_source_path", "pipeline_source_video", "api_source_path"):
                sp = st.session_state.get(key)
                if sp and Path(sp).exists():
                    display_path = Path(sp)
                    break
        if display_path is None and preview_path and preview_path.exists():
            display_path = preview_path
        if display_path is None:
            saved = st.session_state.get("lab_preview_path")
            if saved and Path(saved).exists():
                display_path = Path(saved)

        if display_path:
            st.caption(display_path.name)
            st.video(str(display_path))
        else:
            render_empty("Select a sample above or upload a file.")
    with right:
        st.markdown("**Annotated**")
        if annotated_path and annotated_path.exists() and annotated_path.stat().st_size > 5000:
            st.video(str(annotated_path))
        else:
            render_empty("Run processing to generate annotated output.")

    render_section("Run detection")
    if sample_names and choice:
        out = st.text_input("Output label", value=out_default, key="out_sample")
        if st.button("Process selected sample", type="primary"):
            queue_job(samples_dir / choice, out)
    elif not sample_names:
        render_empty("Put .mp4 files in data/samples/.")


def render_incidents_screen(
    *,
    store: IncidentStore,
    incidents_dir: Path,
    output_dir: Path,
    load_incidents_fn,
    confirm_fn: Callable[[str], None],
    dismiss_fn: Callable[[str], None],
) -> None:
    render_section("Incident registry", "Review evidence images — confirm sends demo dispatch/SMS log entry.")

    f1, f2, f3 = st.columns(3)
    with f1:
        severity_filter = st.selectbox("Severity", ["All", "near_miss", "collision", "severe"], index=0)
    with f2:
        state_filter = st.selectbox(
            "State",
            ["pending_review", "All", "confirmed", "dismissed"],
            index=0,
        )
    with f3:
        only_with_image = st.checkbox("Only with keyframe/clip", value=False)

    sev = None if severity_filter == "All" else severity_filter
    state = None if state_filter == "All" else state_filter
    incidents = asyncio.run(load_incidents_fn(severity=sev, state=state))

    if only_with_image:
        filtered = []
        for inc in incidents:
            iid = inc["id"]
            if (incidents_dir / f"{iid}_keyframe.jpg").exists() or (incidents_dir / f"{iid}.mp4").exists():
                filtered.append(inc)
        incidents = filtered

    render_stat_grid([("Matching", str(len(incidents)), "")])

    page_size = 12
    total_pages = max(1, (len(incidents) + page_size - 1) // page_size)
    page_num = st.number_input("Page", 1, total_pages, 1)
    page_slice = incidents[(page_num - 1) * page_size : page_num * page_size]

    for inc in page_slice:
        disp = normalize_dispatch_status(inc.get("dispatch_status"))
        sev = inc.get("severity", "unknown")
        timecode = format_video_time(float(inc.get("timestamp_sec", 0)))
        with st.container(border=True):
            img_col, info_col, act_col = st.columns([1.1, 1.4, 0.9])
            with img_col:
                kf = incidents_dir / f"{inc['id']}_keyframe.jpg"
                clip = incidents_dir / f"{inc['id']}.mp4"
                if kf.exists():
                    st.image(str(kf), caption=timecode, width="stretch")
                elif clip.exists():
                    st.video(str(clip))
                else:
                    st.markdown(
                        '<div style="height:120px;background:#1a1e24;display:flex;align-items:center;justify-content:center;color:#5f6872;font-size:0.75rem;">No image yet</div>',
                        unsafe_allow_html=True,
                    )
            with info_col:
                st.markdown(f"**{sev.upper()}** · {inc.get('event_type', '')} · **{timecode}**")
                st.caption(f"Score {inc.get('score', 0):.2f} · {disp} · ID `{inc['id'][:10]}…`")
                st.write("Signals:", ", ".join(inc.get("signals") or []) or "—")
                if inc.get("plate_numbers"):
                    st.write("Plates:", ", ".join(inc.get("plate_numbers")))
            with act_col:
                if inc.get("state") == "pending_review":
                    if st.button("Confirm & dispatch", key=f"ir_c_{inc['id']}", type="primary", width="stretch"):
                        confirm_fn(inc["id"])
                        st.success("Saved + dispatch log (demo SMS/call).")
                        st.rerun()
                    if st.button("Not an accident", key=f"ir_d_{inc['id']}", width="stretch"):
                        dismiss_fn(inc["id"])
                        st.rerun()
                else:
                    st.caption(f"State: {inc.get('state')}")


def render_dispatch_screen(logs: list, incidents_dir: Path, road) -> None:
    render_section("Dispatch log", "Police / ambulance routing and call trail (demo simulation).")
    if not logs:
        render_empty("Confirm an incident or use TRIGGER TEST DISPATCH on Live operations.")
        return
    enriched = []
    for row in logs:
        iid = row.get("incident_id", "")
        clip = incidents_dir / f"{iid}.mp4"
        loc = road.location.label
        channel = row.get("channel", "")
        dtype = "Police" if "police" in str(row.get("action", "")).lower() else (
            "Ambulance" if "ambulance" in str(row.get("action", "")).lower() else channel
        )
        enriched.append(
            {
                **row,
                "type": dtype,
                "location": loc,
                "clip": "Available" if clip.exists() else "—",
                "created_at": datetime.fromtimestamp(row.get("created_at", 0)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    render_html_table(
        enriched,
        [
            ("created_at", "Time"),
            ("type", "Type"),
            ("target", "Number"),
            ("location", "Location"),
            ("incident_id", "Incident ID"),
            ("status", "Status"),
            ("clip", "Clip"),
        ],
    )


def render_cameras_screen(settings: Settings, pipeline_busy: bool) -> None:
    from storage.runtime_settings import get_camera_config, set_camera_config

    render_section("Cameras & health", "Feed registry for ESP / RTSP / demo sites.")
    cam = get_camera_config()
    log_path = settings.resolve_path("data/pipeline_last_run.log")
    log_age = time.time() - log_path.stat().st_mtime if log_path.exists() else None
    online = pipeline_busy or (log_age is not None and log_age < 120)

    with st.expander("Configure primary camera", expanded=not cam.get("url")):
        name = st.text_input("Camera name", value=cam["name"])
        url = st.text_input("Stream URL (RTSP or MJPEG HTTP)", value=cam.get("url", ""))
        if st.button("Save camera"):
            set_camera_config(name, url)
            st.rerun()

    feeds = [
        {
            "name": cam["name"],
            "url": cam["url_masked"],
            "status": "Online" if online else "Offline",
            "last_frame_age": f"{int(log_age)}s ago" if log_age is not None else "—",
            "fps": parse_pipeline_fps(log_path) or "—",
        },
        {
            "name": "Site B · Highway (demo)",
            "url": "rtsp://***@demo.local/feeds/b",
            "status": "Offline",
            "last_frame_age": "—",
            "fps": "—",
        },
        {
            "name": "Site C · Toll plaza (demo)",
            "url": "http://***.local/stream",
            "status": "Offline",
            "last_frame_age": "—",
            "fps": "—",
        },
    ]
    render_html_table(
        feeds,
        [
            ("name", "Camera"),
            ("url", "URL"),
            ("status", "Status"),
            ("last_frame_age", "Last activity"),
            ("fps", "FPS"),
        ],
    )
    st.caption("Live preview uses the primary URL on the Live operations tab.")


def render_analytics_screen(summary: dict, timeline: list, pins: list) -> None:
    render_section("Analytics", "Today's activity and event timeline.")
    today = summary.get("today_by_severity") or {}
    collisions = today.get("collision", 0) + today.get("severe", 0)
    near = today.get("near_miss", 0)
    render_stat_grid(
        [
            ("Collisions today", str(collisions), "critical" if collisions else ""),
            ("Near-misses today", str(near), "warning" if near else ""),
            ("Pending review", str(summary.get("pending_review", 0)), ""),
        ]
    )

    if timeline:
        import pandas as pd

        df = pd.DataFrame(timeline)
        df["time"] = df["created_at"].apply(lambda t: datetime.fromtimestamp(t).strftime("%H:%M"))
        try:
            import plotly.express as px
            from dashboard.theme import COLORS

            fig = px.scatter(
                df,
                x="time",
                y="score",
                color="severity",
                size=[8] * len(df),
                height=280,
            )
            fig.update_layout(
                paper_bgcolor=COLORS["surface"],
                plot_bgcolor=COLORS["bg"],
                font_color=COLORS["text_secondary"],
            )
            st.plotly_chart(fig, width="stretch")
        except ImportError:
            st.line_chart(df.set_index("time")["score"])
    else:
        render_empty("No timeline data yet.")

    render_section("Hotspot map")
    if pins:
        st.map(
            {
                "lat": [p["latitude"] for p in pins],
                "lon": [p["longitude"] for p in pins],
            }
        )
    else:
        render_empty("No GPS pins — incidents use demo location from settings.")

    render_section("All-time severity")
    render_analytics_bars(summary.get("by_severity") or {})

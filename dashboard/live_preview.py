"""Live preview panel — last keyframe or optional RTSP snapshot."""

from __future__ import annotations

from pathlib import Path

import cv2
import streamlit as st

from dashboard.utils import find_preview_image


def capture_rtsp_frame(url: str, dest: Path) -> bool:
    if not url:
        return False
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        cap.release()
        return False
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(dest), frame)
    return dest.exists()


@st.fragment(run_every=3)
def render_live_preview(
    incidents_dir: Path,
    output_dir: Path,
    rtsp_url: str | None = None,
    live_snapshot: Path | None = None,
) -> None:
    snap = live_snapshot or (incidents_dir.parent / "live_preview.jpg")
    if rtsp_url:
        capture_rtsp_frame(rtsp_url, snap)
    path = find_preview_image(incidents_dir, output_dir)
    if path and path.suffix.lower() in {".jpg", ".jpeg", ".png"}:
        st.image(str(path), caption="Live / last frame", width="stretch")
    elif path and path.suffix.lower() == ".mp4":
        st.video(str(path))
        st.caption("Showing latest annotated export (no keyframe yet).")
    else:
        st.info("No preview yet. Run detection on a sample or start `run_live.py` with your ESP stream.")

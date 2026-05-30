from __future__ import annotations

from dataclasses import dataclass


# Empirical throughput estimates (720p input, imgsz=640) — use for planning / UI hints.
MODEL_FPS_CPU: dict[str, float] = {
    "yolov8n.pt": 18.0,
    "yolov8s.pt": 12.0,
    "yolov8m.pt": 7.0,
}
MODEL_FPS_GPU: dict[str, float] = {
    "yolov8n.pt": 95.0,
    "yolov8s.pt": 65.0,
    "yolov8m.pt": 40.0,
}

TRACKER_OVERHEAD = 0.05
OPTICAL_FLOW_COST_PER_FRAME = 0.012  # seconds on CPU at 320x180
ANNOTATION_COST_PER_FRAME = 0.004
CLIP_COST_PER_CANDIDATE = 0.05


@dataclass
class PerformanceEstimate:
    model: str
    device: str
    video_width: int
    video_height: int
    fps_source: float
    optical_flow_interval: int
    estimated_pipeline_fps: float
    estimated_realtime_factor: float
    can_run_realtime: bool
    notes: list[str]


def estimate_pipeline_fps(
    model: str,
    device: str,
    video_width: int = 1280,
    video_height: int = 720,
    source_fps: float = 25.0,
    optical_flow_interval: int = 3,
    half_precision: bool = False,
) -> PerformanceEstimate:
    base_table = MODEL_FPS_GPU if device.lower().startswith("cuda") else MODEL_FPS_CPU
    base_fps = base_table.get(model, base_table.get("yolov8n.pt", 15.0))

    pixel_scale = (video_width * video_height) / (1280 * 720)
    base_fps /= max(pixel_scale**0.35, 0.75)

    tracker_fps = base_fps * (1.0 - TRACKER_OVERHEAD)

    flow_frames_per_sec = source_fps / max(optical_flow_interval, 1)
    flow_penalty_fps = flow_frames_per_sec * OPTICAL_FLOW_COST_PER_FRAME
    flow_penalty_fps += source_fps * ANNOTATION_COST_PER_FRAME

    pipeline_fps = max(tracker_fps - flow_penalty_fps, 1.0)
    if half_precision and device.lower().startswith("cuda"):
        pipeline_fps *= 1.25

    realtime_factor = pipeline_fps / max(source_fps, 1.0)
    notes: list[str] = []
    if device == "cpu":
        notes.append("CPU mode: expect ~10–20 FPS at 720p with yolov8n.")
    if optical_flow_interval > 1:
        notes.append(f"Optical flow every {optical_flow_interval} frames saves ~{int(100 / optical_flow_interval)}% flow cost.")
    if realtime_factor < 1.0:
        notes.append("Pipeline slower than source FPS — video will take longer than realtime to process.")
    else:
        notes.append("Pipeline can keep up with source FPS in near-realtime.")

    return PerformanceEstimate(
        model=model,
        device=device,
        video_width=video_width,
        video_height=video_height,
        fps_source=source_fps,
        optical_flow_interval=optical_flow_interval,
        estimated_pipeline_fps=round(pipeline_fps, 1),
        estimated_realtime_factor=round(realtime_factor, 2),
        can_run_realtime=realtime_factor >= 1.0,
        notes=notes,
    )


def format_estimate(est: PerformanceEstimate) -> str:
    lines = [
        f"Model: {est.model} | Device: {est.device} | Input: {est.video_width}x{est.video_height} @ {est.fps_source} FPS",
        f"Estimated pipeline throughput: ~{est.estimated_pipeline_fps} FPS",
        f"Realtime factor: {est.estimated_realtime_factor}x ({'OK' if est.can_run_realtime else 'below realtime'})",
    ]
    lines.extend(f"  - {n}" for n in est.notes)
    return "\n".join(lines)

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

import cv2
import numpy as np

from core.tracker import TrackedObject


def bbox_center(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox
    return ((x1 + x2) / 2, (y1 + y2) / 2)


@dataclass
class TrackState:
    path: deque[tuple[float, float]] = field(default_factory=lambda: deque(maxlen=60))
    speeds: deque[float] = field(default_factory=lambda: deque(maxlen=30))
    last_bbox: tuple[float, float, float, float] | None = None
    last_seen_frame: int = 0
    missing_frames: int = 0


@dataclass
class MotionSnapshot:
    track_id: int
    centroid: tuple[float, float]
    velocity: tuple[float, float]
    speed: float
    acceleration: float
    heading_change: float
    bbox: tuple[float, float, float, float]
    path: list[tuple[float, float]]


class MotionAnalyzer:
    def __init__(
        self,
        meters_per_pixel: float | None = None,
        optical_flow_interval: int = 1,
    ) -> None:
        self.meters_per_pixel = meters_per_pixel
        self.optical_flow_interval = max(1, optical_flow_interval)
        self.tracks: dict[int, TrackState] = {}
        self._prev_gray: np.ndarray | None = None
        self._flow_magnitude: float = 0.0
        self._frame_counter = 0

    def update_optical_flow(self, frame: np.ndarray) -> float | None:
        """Compute Farneback flow every N frames; return None when skipped (reuse last value)."""
        self._frame_counter += 1
        if self._frame_counter % self.optical_flow_interval != 0:
            return None

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 180))
        if self._prev_gray is not None:
            flow = cv2.calcOpticalFlowFarneback(
                self._prev_gray, gray, None, 0.5, 3, 15, 3, 5, 1.2, 0
            )
            mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
            self._flow_magnitude = float(np.mean(mag))
        self._prev_gray = gray
        return self._flow_magnitude

    @property
    def scene_flow_magnitude(self) -> float:
        return self._flow_magnitude

    def update(self, tracked_objects: list[TrackedObject], frame_index: int) -> list[MotionSnapshot]:
        active_ids = {obj.track_id for obj in tracked_objects}
        snapshots: list[MotionSnapshot] = []

        for obj in tracked_objects:
            state = self.tracks.setdefault(obj.track_id, TrackState())
            centroid = bbox_center(obj.bbox)
            state.path.append(centroid)
            state.last_bbox = obj.bbox
            state.last_seen_frame = frame_index
            state.missing_frames = 0

            velocity = (0.0, 0.0)
            speed = 0.0
            acceleration = 0.0
            heading_change = 0.0

            if len(state.path) >= 2:
                prev = state.path[-2]
                velocity = (centroid[0] - prev[0], centroid[1] - prev[1])
                speed = math.hypot(*velocity)
                if self.meters_per_pixel:
                    speed *= self.meters_per_pixel

            if len(state.path) >= 6:
                older = state.path[-6]
                prev_velocity = (centroid[0] - older[0], centroid[1] - older[1])
                prev_speed = math.hypot(*prev_velocity)
                if self.meters_per_pixel:
                    prev_speed *= self.meters_per_pixel
                acceleration = speed - prev_speed

            if len(state.path) >= 10:
                p1, p2, p3 = state.path[-10], state.path[-5], state.path[-1]
                v1 = (p2[0] - p1[0], p2[1] - p1[1])
                v2 = (p3[0] - p2[0], p3[1] - p2[1])
                dot = v1[0] * v2[0] + v1[1] * v2[1]
                mag1, mag2 = math.hypot(*v1) or 1e-6, math.hypot(*v2) or 1e-6
                cos_angle = max(-1.0, min(1.0, dot / (mag1 * mag2)))
                heading_change = math.degrees(math.acos(cos_angle))

            state.speeds.append(speed)
            snapshots.append(
                MotionSnapshot(
                    track_id=obj.track_id,
                    centroid=centroid,
                    velocity=velocity,
                    speed=speed,
                    acceleration=acceleration,
                    heading_change=heading_change,
                    bbox=obj.bbox,
                    path=list(state.path),
                )
            )

        for track_id in list(self.tracks):
            if track_id not in active_ids:
                self.tracks[track_id].missing_frames += 1
                if self.tracks[track_id].missing_frames > 30:
                    del self.tracks[track_id]

        return snapshots

    def speed_drop_ratio(self, track_id: int, window: int = 5) -> float:
        state = self.tracks.get(track_id)
        if not state or len(state.speeds) < window + 1:
            return 0.0
        recent = list(state.speeds)
        prev_speed = max(recent[-window - 1], 1e-6)
        curr_speed = recent[-1]
        if prev_speed < 1.0:
            return 0.0
        return max(0.0, (prev_speed - curr_speed) / prev_speed)

    def track_lost_after_overlap(self, track_id: int) -> bool:
        state = self.tracks.get(track_id)
        return state is None or state.missing_frames >= 2

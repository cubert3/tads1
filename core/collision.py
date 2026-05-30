from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.config import CollisionConfig, NearMissConfig
from core.motion import MotionAnalyzer, MotionSnapshot, bbox_center


def compute_iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    if inter <= 0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def center_distance(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ca, cb = bbox_center(a), bbox_center(b)
    return math.hypot(ca[0] - cb[0], ca[1] - cb[1])


def approach_rate(
    ca: tuple[float, float], cb: tuple[float, float],
    va: tuple[float, float], vb: tuple[float, float],
) -> float:
    rel_pos = (cb[0] - ca[0], cb[1] - ca[1])
    rel_vel = (vb[0] - va[0], vb[1] - va[1])
    dist = math.hypot(*rel_pos) or 1e-6
    return -((rel_pos[0] / dist) * rel_vel[0] + (rel_pos[1] / dist) * rel_vel[1])


@dataclass
class ScoredEvent:
    event_type: str
    severity: str
    score: float
    signals: list[str] = field(default_factory=list)
    track_ids: tuple[int, int] | None = None
    location: tuple[float, float] | None = None
    frame_index: int = 0
    timestamp_sec: float = 0.0


class CollisionScorer:
    SIGNAL_WEIGHTS = {
        "overlap": 0.35,
        "convergence": 0.20,
        "decel": 0.25,
        "trajectory_anomaly": 0.15,
        "track_loss": 0.10,
        "flow_spike": 0.10,
    }

    def __init__(
        self,
        collision_config: CollisionConfig,
        near_miss_config: NearMissConfig,
        motion: MotionAnalyzer,
    ) -> None:
        self.collision_config = collision_config
        self.near_miss_config = near_miss_config
        self.motion = motion
        self._overlap_streak: dict[tuple[int, int], int] = {}

    def evaluate(
        self,
        snapshots: list[MotionSnapshot],
        frame_index: int,
        timestamp_sec: float,
        flow_magnitude: float,
        flow_baseline: float,
    ) -> list[ScoredEvent]:
        events: list[ScoredEvent] = []
        for i in range(len(snapshots)):
            for j in range(i + 1, len(snapshots)):
                ev = self._score_pair(snapshots[i], snapshots[j], frame_index, timestamp_sec, flow_magnitude, flow_baseline)
                if ev:
                    events.append(ev)
        return events

    def _score_pair(
        self, a: MotionSnapshot, b: MotionSnapshot,
        frame_index: int, timestamp_sec: float,
        flow_magnitude: float, flow_baseline: float,
    ) -> ScoredEvent | None:
        iou = compute_iou(a.bbox, b.bbox)
        dist = center_distance(a.bbox, b.bbox)
        closing = approach_rate(a.centroid, b.centroid, a.velocity, b.velocity)
        pair_key = tuple(sorted((a.track_id, b.track_id)))

        if iou > self.collision_config.iou_threshold:
            self._overlap_streak[pair_key] = self._overlap_streak.get(pair_key, 0) + 1
        else:
            self._overlap_streak[pair_key] = 0

        signals: list[str] = []
        score = 0.0

        if self._overlap_streak.get(pair_key, 0) >= 2:
            signals.append("overlap")
            score += self.SIGNAL_WEIGHTS["overlap"]
        if dist < self.near_miss_config.proximity_px and closing > self.near_miss_config.approach_rate_min:
            signals.append("convergence")
            score += self.SIGNAL_WEIGHTS["convergence"]
        if self.motion.speed_drop_ratio(a.track_id) > self.collision_config.decel_threshold or \
           self.motion.speed_drop_ratio(b.track_id) > self.collision_config.decel_threshold:
            signals.append("decel")
            score += self.SIGNAL_WEIGHTS["decel"]
        if a.heading_change > 90 or b.heading_change > 90:
            signals.append("trajectory_anomaly")
            score += self.SIGNAL_WEIGHTS["trajectory_anomaly"]
        if iou > 0.1 and (self.motion.track_lost_after_overlap(a.track_id) or self.motion.track_lost_after_overlap(b.track_id)):
            signals.append("track_loss")
            score += self.SIGNAL_WEIGHTS["track_loss"]
        if flow_baseline > 0 and flow_magnitude > flow_baseline * 1.8:
            signals.append("flow_spike")
            score += self.SIGNAL_WEIGHTS["flow_spike"]

        if not signals:
            return None

        mid = ((a.centroid[0] + b.centroid[0]) / 2, (a.centroid[1] + b.centroid[1]) / 2)

        if "convergence" in signals and iou < self.collision_config.iou_threshold and dist <= self.near_miss_config.proximity_px:
            return ScoredEvent("near_miss", "near_miss", score, signals, (a.track_id, b.track_id), mid, frame_index, timestamp_sec)

        if len(signals) >= self.collision_config.min_signals and score >= 0.35:
            severity = "severe" if ("overlap" in signals and "decel" in signals) else "collision"
            return ScoredEvent("collision", severity, score, signals, (a.track_id, b.track_id), mid, frame_index, timestamp_sec)

        return None

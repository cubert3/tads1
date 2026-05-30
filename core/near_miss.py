"""Near-miss detection — re-exports collision scorer types for modular imports."""

from core.collision import CollisionScorer, ScoredEvent, approach_rate, center_distance, compute_iou

__all__ = [
    "CollisionScorer",
    "ScoredEvent",
    "compute_iou",
    "center_distance",
    "approach_rate",
]

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from core.config import CalibrationConfig


@dataclass
class CalibrationResult:
    meters_per_pixel: float
    homography: np.ndarray | None = None


class HomographyCalibrator:
    def __init__(self, config: CalibrationConfig) -> None:
        self.config = config
        self.meters_per_pixel = config.meters_per_pixel
        self.homography = None
        if config.enabled and len(config.reference_points) == 4:
            self._compute_from_points(config.reference_points)

    def _compute_from_points(self, points: list[list[float]]) -> None:
        src = np.array(points[:4], dtype=np.float32)
        dst = np.array([[0, 0], [3.5, 0], [3.5, 7.0], [0, 7.0]], dtype=np.float32)
        self.homography = cv2.getPerspectiveTransform(src, dst)
        pixel_width = np.linalg.norm(src[0] - src[1])
        self.meters_per_pixel = 3.5 / max(pixel_width, 1e-6)

    def speed_px_to_kmh(self, speed_px_per_frame: float, fps: float) -> float:
        if self.meters_per_pixel is None:
            return speed_px_per_frame * fps
        return speed_px_per_frame * self.meters_per_pixel * fps * 3.6

    @staticmethod
    def from_lane_width(pixel_lane_width: float, lane_width_m: float = 3.5) -> CalibrationResult:
        return CalibrationResult(meters_per_pixel=lane_width_m / max(pixel_lane_width, 1e-6))

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

from core.config import DetectionConfig

VEHICLE_CLASSES = {2, 3, 5, 7}
ALL_TARGET_CLASSES = sorted(VEHICLE_CLASSES | {0})


@dataclass
class Detection:
    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str


class VehicleDetector:
    def __init__(self, config: DetectionConfig, model: YOLO | None = None, half: bool = False) -> None:
        self.config = config
        self.model = model or YOLO(config.model)
        self.half = half and config.device.lower().startswith("cuda")

    def detect(self, frame: np.ndarray) -> list[Detection]:
        results = self.model(
            frame,
            classes=ALL_TARGET_CLASSES,
            conf=self.config.conf,
            imgsz=self.config.imgsz,
            device=self.config.device,
            half=self.half,
            verbose=False,
        )
        detections: list[Detection] = []
        if not results or results[0].boxes is None:
            return detections

        result = results[0]
        names = result.names or {}
        for box in result.boxes:
            xyxy = box.xyxy[0].tolist()
            class_id = int(box.cls[0])
            detections.append(
                Detection(
                    bbox=(xyxy[0], xyxy[1], xyxy[2], xyxy[3]),
                    confidence=float(box.conf[0]),
                    class_id=class_id,
                    class_name=str(names.get(class_id, class_id)),
                )
            )
        return detections

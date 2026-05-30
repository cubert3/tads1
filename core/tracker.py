from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import supervision as sv
from ultralytics import YOLO

from core.config import DetectionConfig, TrackingConfig

VEHICLE_CLASSES = {0, 2, 3, 5, 7}


@dataclass
class TrackedObject:
    track_id: int
    bbox: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str


class VehicleTracker:
    TRACKER_MAP = {
        "botsort": "botsort.yaml",
        "bytetrack": "bytetrack.yaml",
        "strongsort": "strongsort.yaml",
    }

    def __init__(
        self,
        detection_config: DetectionConfig,
        tracking_config: TrackingConfig,
        model: YOLO | None = None,
        half: bool = False,
    ) -> None:
        self.detection_config = detection_config
        self.tracking_config = tracking_config
        self.model = model or YOLO(detection_config.model)
        self.half = half and detection_config.device.lower().startswith("cuda")
        backend = tracking_config.backend.lower()
        self.tracker_yaml = self.TRACKER_MAP.get(backend, "botsort.yaml")

    def track(self, frame: np.ndarray) -> tuple[list[TrackedObject], sv.Detections]:
        results = self.model.track(
            frame,
            persist=self.tracking_config.persist,
            tracker=self.tracker_yaml,
            classes=sorted(VEHICLE_CLASSES),
            conf=self.detection_config.conf,
            imgsz=self.detection_config.imgsz,
            device=self.detection_config.device,
            half=self.half,
            verbose=False,
        )

        if not results or results[0].boxes is None:
            return [], sv.Detections.empty()

        result = results[0]
        detections = sv.Detections.from_ultralytics(result)
        names = result.names or {}
        tracked: list[TrackedObject] = []

        if detections.tracker_id is None:
            return tracked, detections

        for i in range(len(detections)):
            track_id = detections.tracker_id[i]
            if track_id is None or track_id < 0:
                continue
            xyxy = detections.xyxy[i]
            class_id = int(detections.class_id[i]) if detections.class_id is not None else -1
            conf = float(detections.confidence[i]) if detections.confidence is not None else 0.0
            tracked.append(
                TrackedObject(
                    track_id=int(track_id),
                    bbox=(float(xyxy[0]), float(xyxy[1]), float(xyxy[2]), float(xyxy[3])),
                    confidence=conf,
                    class_id=class_id,
                    class_name=str(names.get(class_id, class_id)),
                )
            )
        return tracked, detections

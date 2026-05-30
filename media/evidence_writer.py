from __future__ import annotations

import json
import logging
from collections import deque
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from core.config import EvidenceConfig

logger = logging.getLogger(__name__)


@dataclass
class BufferedFrame:
    timestamp_sec: float
    raw: np.ndarray
    annotated: np.ndarray


class EvidenceWriter:
    def __init__(self, config: EvidenceConfig, incidents_dir: Path, fps: float) -> None:
        self.config = config
        self.incidents_dir = incidents_dir
        self.fps = fps
        self.incidents_dir.mkdir(parents=True, exist_ok=True)
        pre_frames = max(1, int(config.pre_seconds * fps))
        self._buffer: deque[BufferedFrame] = deque(maxlen=pre_frames)
        self._post_remaining = 0
        self._writer: cv2.VideoWriter | None = None
        self._current_incident_id: str | None = None
        self._current_paths: dict[str, Path] = {}

    def push(self, timestamp_sec: float, raw: np.ndarray, annotated: np.ndarray) -> None:
        self._buffer.append(BufferedFrame(timestamp_sec, raw.copy(), annotated.copy()))
        if self._post_remaining > 0 and self._writer is not None:
            self._writer.write(annotated)
            self._post_remaining -= 1
            if self._post_remaining == 0:
                self._finalize_clip()

    def start_capture(self, incident_id: str) -> tuple[Path, Path]:
        self._current_incident_id = incident_id
        clip_path = self.incidents_dir / f"{incident_id}.mp4"
        keyframe_path = self.incidents_dir / f"{incident_id}_keyframe.jpg"
        self._current_paths = {"clip": clip_path, "keyframe": keyframe_path}

        if not self._buffer:
            return clip_path, keyframe_path

        h, w = self._buffer[0].annotated.shape[:2]
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(str(clip_path), fourcc, self.fps, (w, h))
        for item in self._buffer:
            self._writer.write(item.annotated)
        cv2.imwrite(str(keyframe_path), self._buffer[-1].annotated)
        self._post_remaining = max(1, int(self.config.post_seconds * self.fps))
        return clip_path, keyframe_path

    def _finalize_clip(self) -> None:
        if self._writer:
            self._writer.release()
            self._writer = None
        logger.info("Evidence saved: %s", self._current_incident_id)

    def save_metadata(self, incident_id: str, metadata: dict) -> Path:
        path = self.incidents_dir / f"{incident_id}.json"
        with path.open("w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2, default=str)
        return path

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2


@dataclass
class VideoSource:
    path: str | None = None
    camera_index: int | None = None
    rtsp_url: str | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> VideoSource:
        return cls(path=str(path))

    @classmethod
    def from_camera(cls, index: int = 0) -> VideoSource:
        return cls(camera_index=index)

    @classmethod
    def from_rtsp(cls, url: str) -> VideoSource:
        return cls(rtsp_url=url)

    def open(self) -> cv2.VideoCapture:
        if self.path:
            cap = cv2.VideoCapture(self.path)
        elif self.rtsp_url:
            cap = cv2.VideoCapture(self.rtsp_url)
        elif self.camera_index is not None:
            cap = cv2.VideoCapture(self.camera_index)
        else:
            raise ValueError("No valid video source configured")
        if not cap.isOpened():
            raise RuntimeError(f"Failed to open video source: {self}")
        return cap

    def __str__(self) -> str:
        return self.path or self.rtsp_url or f"camera:{self.camera_index}"


@dataclass
class FramePacket:
    index: int
    timestamp_sec: float
    frame: object


class VideoReader:
    def __init__(self, source: VideoSource) -> None:
        self.source = source
        self.cap = source.open()
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 25.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)

    def __iter__(self) -> Iterator[FramePacket]:
        index = 0
        while True:
            ok, frame = self.cap.read()
            if not ok:
                break
            yield FramePacket(index=index, timestamp_sec=index / self.fps, frame=frame)
            index += 1

    def release(self) -> None:
        self.cap.release()

    def __enter__(self) -> VideoReader:
        return self

    def __exit__(self, *args: object) -> None:
        self.release()

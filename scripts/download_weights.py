#!/usr/bin/env python3
"""Download YOLOv8 pretrained weights."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ultralytics import YOLO


def main() -> None:
    models = ["yolov8n.pt", "yolov8s.pt"]
    for name in models:
        print(f"Downloading {name}...")
        YOLO(name)
        print(f"  OK: {name}")


if __name__ == "__main__":
    main()

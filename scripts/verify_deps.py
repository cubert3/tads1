#!/usr/bin/env python3
"""Verify all project dependencies import correctly."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, str]] = [
    ("numpy", "import numpy"),
    ("scipy", "import scipy"),
    ("cv2", "import cv2"),
    ("yaml", "import yaml"),
    ("pydantic", "import pydantic"),
    ("httpx", "import httpx"),
    ("aiosqlite", "import aiosqlite"),
    ("supervision", "import supervision"),
    ("ultralytics", "from ultralytics import YOLO"),
    ("lap", "import lap"),
    ("torch", "import torch"),
    ("torchvision", "import torchvision"),
    ("fastapi", "import fastapi"),
    ("uvicorn", "import uvicorn"),
    ("streamlit", "import streamlit"),
    ("plotly", "import plotly"),
    ("pandas", "import pandas"),
    ("transformers", "import transformers"),
    ("pytesseract", "import pytesseract"),
    ("pytest", "import pytest"),
    ("trackers", "from ultralytics.trackers import register_tracker"),
    ("tads.core", "from core.config import get_settings"),
    ("tads.processor", "from core.processor import AccidentDetectionProcessor"),
]

# Optional: Tesseract binary on PATH (not a pip package)
TESSERACT_NOTE = "Tesseract OCR binary (optional, for plates): install from https://github.com/UB-Mannheim/tesseract/wiki"


def main() -> int:
    failed: list[str] = []
    print("Checking dependencies...\n")
    for name, stmt in CHECKS:
        try:
            exec(stmt, {})
            print(f"  OK  {name}")
        except Exception as exc:
            print(f"  FAIL {name}: {exc}")
            failed.append(name)

    weights = ROOT / "yolov8n.pt"
    if weights.exists():
        print(f"  OK  yolov8n.pt ({weights.stat().st_size // 1024} KB)")
    else:
        print("  WARN yolov8n.pt missing — run: python scripts/download_weights.py")
        failed.append("yolov8n.pt")

    print(f"\n{TESSERACT_NOTE}")

    if failed:
        print(f"\nFailed ({len(failed)}): {', '.join(failed)}")
        print("Run: .\\scripts\\install_deps.ps1")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

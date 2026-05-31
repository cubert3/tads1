#!/usr/bin/env python3
"""Prepare sample video folder and print download instructions."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import get_settings

MANIFEST = {
    "description": "Place test videos in data/samples/ for evaluation",
    "recommended_clips": [
        {
            "filename": "normal_traffic.mp4",
            "label": False,
            "description": "30-60s intersection or highway, no incident",
        },
        {
            "filename": "crash_clip.mp4",
            "label": True,
            "description": "Dashcam or CCTV clip with visible collision",
        },
        {
            "filename": "near_miss.mp4",
            "label": False,
            "description": "Optional — close call without contact (tests near-miss tier)",
        },
    ],
    "sources": [
        "CADP — Car Accident Detection from Perspective (Google dataset search)",
        "BDD100K — normal driving scenes (bdd-data.berkeley.edu)",
        "YouTube — search 'traffic camera intersection' or 'dashcam accident' (respect copyright for demos)",
    ],
    "commands_after_download": [
        "python scripts/run_video.py --input data/samples/crash_clip.mp4",
        "python scripts/evaluate.py --dir data/samples --labels data/sample_labels.json",
    ],
}


def main() -> None:
    settings = get_settings()
    samples_dir = settings.resolve_path(settings.paths.samples_dir)
    samples_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = samples_dir / "manifest.json"
    manifest_path.write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")

    print(f"Samples directory: {samples_dir}")
    print(f"Wrote manifest: {manifest_path}\n")
    print("Recommended files to add:")
    for clip in MANIFEST["recommended_clips"]:
        label = "incident" if clip["label"] else "normal"
        print(f"  - {clip['filename']} ({label}): {clip['description']}")
    print("\nDataset sources:")
    for src in MANIFEST["sources"]:
        print(f"  - {src}")
    print("\nAfter adding videos:")
    for cmd in MANIFEST["commands_after_download"]:
        print(f"  {cmd}")


if __name__ == "__main__":
    main()

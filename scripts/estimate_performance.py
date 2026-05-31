#!/usr/bin/env python3
"""Print estimated pipeline throughput for current config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.performance import estimate_pipeline_fps, format_estimate


def main() -> None:
    parser = argparse.ArgumentParser(description="Estimate TADS pipeline FPS")
    parser.add_argument("--config", default=None)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=float, default=25.0)
    args = parser.parse_args()

    settings = get_settings(args.config)
    est = estimate_pipeline_fps(
        model=settings.detection.model,
        device=settings.detection.device,
        video_width=args.width,
        video_height=args.height,
        source_fps=args.fps,
        optical_flow_interval=settings.performance.optical_flow_interval,
        half_precision=settings.performance.half_precision,
    )
    print(format_estimate(est))


if __name__ == "__main__":
    main()

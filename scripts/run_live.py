#!/usr/bin/env python3
"""Live processing from webcam or RTSP stream."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.processor import AccidentDetectionProcessor
from media.video_reader import VideoSource

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Live accident detection")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--camera", type=int, help="Webcam index (default 0)")
    group.add_argument("--rtsp", type=str, help="RTSP stream URL")
    parser.add_argument("--output", "-o", default="live_annotated.mp4")
    args = parser.parse_args()

    if args.rtsp:
        source = VideoSource.from_rtsp(args.rtsp)
    else:
        source = VideoSource.from_camera(args.camera if args.camera is not None else 0)

    processor = AccidentDetectionProcessor(settings=get_settings())
    logger.info("Starting live processing: %s", source)
    result = processor.process_source(source, output_name=args.output)
    logger.info("Stopped — %d frames, %d incidents", result.frames_processed, len(result.incidents))


if __name__ == "__main__":
    main()

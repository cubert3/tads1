#!/usr/bin/env python3
"""Batch video processing — outputs annotated demo MP4 + incident evidence."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.config import get_settings
from core.processor import AccidentDetectionProcessor
from media.video_reader import VideoSource
from storage.incident_store import IncidentStore

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def persist_incidents(processor: AccidentDetectionProcessor, result) -> None:
    store = IncidentStore(get_settings().resolve_path(get_settings().paths.database_path))
    for inc in result.incidents:
        await store.save(inc)


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a traffic video for accident detection")
    parser.add_argument("--input", "-i", required=True, help="Path to input video")
    parser.add_argument("--output", "-o", default=None, help="Annotated output filename")
    parser.add_argument("--config", default=None, help="Path to settings.yaml")
    args = parser.parse_args()

    settings = get_settings(args.config)
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("Input not found: %s", input_path)
        sys.exit(1)

    processor = AccidentDetectionProcessor(settings=settings)
    logger.info("Processing: %s", input_path)
    result = processor.process_source(VideoSource.from_file(input_path), output_name=args.output)

    asyncio.run(persist_incidents(processor, result))

    logger.info("Done — %d frames @ %.1f FPS", result.frames_processed, result.fps_avg)
    logger.info("Incidents: %d", len(result.incidents))
    if result.annotated_path:
        logger.info("Annotated video: %s", result.annotated_path)
    for inc in result.incidents:
        logger.info("  [%s] %s score=%.2f @ %.1fs", inc.severity, inc.event_type, inc.score, inc.timestamp_sec)


if __name__ == "__main__":
    main()

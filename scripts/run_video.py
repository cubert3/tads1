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

    from dashboard.pipeline_runner import update_job_progress

    last_logged = 0

    def on_progress(frames: int, total: int, fps: float) -> None:
        nonlocal last_logged
        update_job_progress(frames, total, fps)
        if frames == total or frames - last_logged >= 30:
            last_logged = frames
            logger.info("Progress: %d / %d frames (%.1f fps)", frames, total, fps)

    processor = AccidentDetectionProcessor(settings=settings, on_progress=on_progress)
    logger.info("Processing: %s", input_path)
    result = processor.process_source(VideoSource.from_file(input_path), output_name=args.output)

    asyncio.run(persist_incidents(processor, result))

    from dashboard.run_summary import write_run_summary

    try:
        write_run_summary(
            source_video=str(input_path),
            output_name=args.output,
            incidents=result.incidents,
            frames=result.frames_processed,
            fps=result.fps_avg,
        )
    except Exception as exc:
        logger.exception("Failed to write run summary: %s", exc)

    logger.info("Done — %d frames @ %.1f FPS", result.frames_processed, result.fps_avg)
    if result.performance_estimate:
        logger.info(
            "Estimated vs actual: ~%.1f est / %.1f actual FPS",
            result.performance_estimate.estimated_pipeline_fps,
            result.fps_avg,
        )
    logger.info("Incidents: %d", len(result.incidents))
    if result.annotated_path:
        logger.info("Annotated video: %s", result.annotated_path)
    for inc in result.incidents:
        logger.info("  [%s] %s score=%.2f @ %.1fs", inc.severity, inc.event_type, inc.score, inc.timestamp_sec)


if __name__ == "__main__":
    main()

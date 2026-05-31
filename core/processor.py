from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import cv2
import numpy as np
import supervision as sv

from core.calibration import HomographyCalibrator
from core.clip_filter import ClipFalsePositiveFilter
from core.collision import CollisionScorer
from core.config import Settings, get_settings
from core.cooldown_tracker import CooldownTracker
from core.incident_manager import IncidentManager, IncidentRecord, IncidentState
from core.motion import MotionAnalyzer
from core.performance import PerformanceEstimate, estimate_pipeline_fps
from core.plate_reader import extract_plates_from_tracks
from core.tracker import TrackedObject, VehicleTracker
from media.alerter import Alerter
from media.dispatch import DispatchService
from media.evidence_writer import EvidenceWriter
from media.video_reader import VideoReader, VideoSource
from storage.incident_store import IncidentStore
from storage.runtime_settings import human_confirm_enabled

logger = logging.getLogger(__name__)


@dataclass
class ProcessingResult:
    source: str
    annotated_path: Path | None
    incidents: list[IncidentRecord] = field(default_factory=list)
    frames_processed: int = 0
    fps_avg: float = 0.0
    performance_estimate: PerformanceEstimate | None = None


class AccidentDetectionProcessor:
    def __init__(
        self,
        settings: Settings | None = None,
        alerter: Alerter | None = None,
        on_progress: Callable[[int, int, float], None] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.alerter = alerter or Alerter(self.settings.alerts)
        self.on_progress = on_progress
        perf = self.settings.performance
        road = self.settings.road_sos

        calibrator = HomographyCalibrator(self.settings.calibration)
        mpp = calibrator.meters_per_pixel if self.settings.calibration.enabled else None

        self.motion = MotionAnalyzer(
            meters_per_pixel=mpp,
            optical_flow_interval=perf.optical_flow_interval,
        )
        self.scorer = CollisionScorer(self.settings.collision, self.settings.near_miss, self.motion)
        self.clip_filter = ClipFalsePositiveFilter(self.settings.clip_filter)
        self.tracker = VehicleTracker(
            self.settings.detection,
            self.settings.tracking,
            half=perf.half_precision,
        )
        self.store = IncidentStore(self.settings.resolve_path(self.settings.paths.database_path))
        self.dispatch_service = DispatchService(road)
        self.cooldown_tracker = CooldownTracker(
            self.settings.collision.cooldown_seconds,
            self.settings.collision.cooldown_distance_px,
        )

        self._evidence: EvidenceWriter | None = None
        self._flow_baseline = 0.0
        self._flow_samples = 0
        self._last_flow = 0.0
        self._last_tracked: list[TrackedObject] = []

        self.incident_manager = IncidentManager(
            self.settings.collision,
            self.clip_filter,
            cooldown_tracker=self.cooldown_tracker,
            human_confirm_enabled=human_confirm_enabled(road.human_confirm_enabled),
            on_confirmed=self._on_incident_confirmed,
            on_pending_review=self._on_incident_pending_review,
        )

        self.box_annotator = sv.BoxAnnotator(thickness=2)
        self.label_annotator = sv.LabelAnnotator(text_scale=0.5)
        self.trace_annotator = sv.TraceAnnotator(thickness=2, trace_length=30)

    def _apply_geo_metadata(self, record: IncidentRecord) -> None:
        loc = self.settings.road_sos.location
        record.latitude = loc.latitude
        record.longitude = loc.longitude
        record.location_label = loc.label

    def _on_incident_pending_review(self, record: IncidentRecord, frame: np.ndarray) -> None:
        self._finalize_incident(record, frame, self._last_tracked, run_dispatch=False)

    def _on_incident_confirmed(self, record: IncidentRecord, frame: np.ndarray) -> None:
        self._finalize_incident(record, frame, self._last_tracked, run_dispatch=True)

    def _finalize_incident(
        self,
        record: IncidentRecord,
        frame: np.ndarray,
        tracked: list[TrackedObject],
        run_dispatch: bool,
    ) -> None:
        self._apply_geo_metadata(record)
        record.plate_numbers = extract_plates_from_tracks(
            frame,
            tracked,
            record.track_ids,
            enabled=self.settings.road_sos.plate_detection_enabled,
        )

        if self._evidence is not None:
            clip_path, keyframe_path = self._evidence.start_capture(record.id)
            record.clip_path = str(clip_path)
            record.keyframe_path = str(keyframe_path)
            metadata = {
                "id": record.id,
                "event_type": record.event_type,
                "severity": record.severity,
                "score": record.score,
                "signals": record.signals,
                "track_ids": record.track_ids,
                "plate_numbers": record.plate_numbers,
                "timestamp_sec": record.timestamp_sec,
                "frame_index": record.frame_index,
                "state": record.state.value,
            }
            self._evidence.save_metadata(record.id, metadata)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._persist_incident(record, run_dispatch))
        except RuntimeError:
            asyncio.run(self._persist_incident(record, run_dispatch))

    async def _persist_incident(self, record: IncidentRecord, run_dispatch: bool) -> None:
        await self.store.save(record)
        zones = self.cooldown_tracker.active_zones()
        if zones:
            await self.store.save_cooldown_zones(zones)
        await self.alerter.notify(record)
        if run_dispatch and record.state == IncidentState.CONFIRMED:
            entries = await self.dispatch_service.execute(
                record,
                self.settings.alerts.webhook_url,
                on_persist=self.store.save_dispatch_entries,
            )
            if entries:
                record.dispatch_status = entries[-1].status
                await self.store.save(record)

    async def approve_and_dispatch(self, incident_id: str) -> IncidentRecord | None:
        item = await self.store.get(incident_id)
        if not item or item.get("state") != IncidentState.PENDING_REVIEW.value:
            return None
        record = IncidentStore.record_from_row(item)
        record.state = IncidentState.CONFIRMED
        record.dispatch_status = "pending"
        record.human_reviewed = True
        await self.store.save(record)
        entries = await self.dispatch_service.execute(
            record,
            self.settings.alerts.webhook_url,
            on_persist=self.store.save_dispatch_entries,
        )
        if entries:
            record.dispatch_status = entries[-1].status
            await self.store.save(record)
        await self.alerter.notify(record)
        return record

    async def dismiss_incident(self, incident_id: str) -> bool:
        return await self.store.update_state(
            incident_id,
            IncidentState.DISMISSED.value,
            "dismissed",
            human_reviewed=True,
        )

    def process_source(self, source: VideoSource, output_name: str | None = None) -> ProcessingResult:
        incidents: list[IncidentRecord] = []
        source_str = str(source)
        perf = self.settings.performance

        with VideoReader(source) as reader:
            perf_estimate = estimate_pipeline_fps(
                model=self.settings.detection.model,
                device=self.settings.detection.device,
                video_width=reader.width,
                video_height=reader.height,
                source_fps=reader.fps,
                optical_flow_interval=perf.optical_flow_interval,
                half_precision=perf.half_precision,
            )
            logger.info(
                "Performance estimate: ~%.1f FPS (realtime factor %.2fx)",
                perf_estimate.estimated_pipeline_fps,
                perf_estimate.estimated_realtime_factor,
            )

            self._evidence = EvidenceWriter(
                self.settings.evidence,
                self.settings.resolve_path(self.settings.paths.incidents_dir),
                reader.fps,
            )

            annotated_path: Path | None = None
            writer: cv2.VideoWriter | None = None
            if perf.save_annotated_video:
                output_dir = self.settings.resolve_path(self.settings.paths.output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                out_name = output_name or f"annotated_{Path(source_str).stem}.mp4"
                annotated_path = output_dir / out_name
                writer = cv2.VideoWriter(
                    str(annotated_path),
                    cv2.VideoWriter_fourcc(*"mp4v"),
                    reader.fps,
                    (reader.width, reader.height),
                )

            import time

            start = time.perf_counter()
            frames = 0

            for packet in reader:
                frame = packet.frame  # type: ignore[assignment]
                tracked, detections = self.tracker.track(frame)
                self._last_tracked = tracked

                flow = self.motion.update_optical_flow(frame)
                if flow is not None:
                    self._last_flow = flow
                    self._flow_samples += 1
                    self._flow_baseline += (flow - self._flow_baseline) / self._flow_samples

                snapshots = self.motion.update(tracked, packet.index)
                events = self.scorer.evaluate(
                    snapshots,
                    packet.index,
                    packet.timestamp_sec,
                    self._last_flow,
                    self._flow_baseline,
                )
                confirmed = self.incident_manager.process_events(events, frame)
                incidents.extend(confirmed)

                if perf.show_overlay or perf.save_annotated_video:
                    annotated = self._annotate(frame, detections, confirmed)
                else:
                    annotated = frame

                self._evidence.push(packet.timestamp_sec, annotated)
                if writer is not None:
                    writer.write(annotated)
                frames += 1

                if self.on_progress and reader.frame_count:
                    self.on_progress(frames, reader.frame_count, frames / max(time.perf_counter() - start, 1e-6))

            if writer is not None:
                writer.release()
            elapsed = time.perf_counter() - start
            fps_avg = frames / max(elapsed, 1e-6)

        for inc in self.incident_manager.all_incidents:
            inc.source_video = source_str
            if inc not in incidents:
                incidents.append(inc)

        return ProcessingResult(source_str, annotated_path, incidents, frames, fps_avg, perf_estimate)

    def _annotate(
        self,
        frame: np.ndarray,
        detections: sv.Detections,
        confirmed: list[IncidentRecord],
    ) -> np.ndarray:
        needs_copy = len(detections) > 0 or len(confirmed) > 0
        annotated = frame.copy() if needs_copy else frame

        if len(detections) > 0:
            annotated = self.trace_annotator.annotate(annotated, detections)
            annotated = self.box_annotator.annotate(annotated, detections)
            labels = []
            if detections.tracker_id is not None:
                for i in range(len(detections)):
                    tid = detections.tracker_id[i]
                    conf = detections.confidence[i] if detections.confidence is not None else 0
                    labels.append(f"#{tid} {conf:.2f}")
            if labels:
                annotated = self.label_annotator.annotate(annotated, detections, labels=labels)

        y = 40
        for inc in confirmed:
            color = (0, 0, 255) if inc.event_type == "collision" else (0, 165, 255)
            if inc.state == IncidentState.PENDING_REVIEW:
                color = (0, 255, 255)
            label = f"{inc.severity.upper()} score={inc.score:.2f}"
            if inc.state == IncidentState.PENDING_REVIEW:
                label += " REVIEW"
            cv2.putText(annotated, label, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
            y += 35
        return annotated

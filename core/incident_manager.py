from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

import numpy as np

from core.clip_filter import ClipFalsePositiveFilter, ClipVerdict
from core.collision import ScoredEvent
from core.config import CollisionConfig
from core.cooldown_tracker import CooldownTracker


class IncidentState(str, Enum):
    CANDIDATE = "candidate"
    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    ARCHIVED = "archived"


@dataclass
class IncidentRecord:
    id: str
    state: IncidentState
    event_type: str
    severity: str
    score: float
    signals: list[str]
    track_ids: tuple[int, int] | None
    location: tuple[float, float] | None
    frame_index: int
    timestamp_sec: float
    candidate_frames: int = 0
    clip_verdict: ClipVerdict | None = None
    created_at: float = field(default_factory=time.time)
    confirmed_at: float | None = None
    clip_path: str | None = None
    keyframe_path: str | None = None
    source_video: str | None = None
    dispatch_status: str = "pending"
    plate_numbers: list[str] = field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    location_label: str | None = None
    human_reviewed: bool = False


class IncidentManager:
    def __init__(
        self,
        collision_config: CollisionConfig,
        clip_filter: ClipFalsePositiveFilter,
        cooldown_tracker: CooldownTracker | None = None,
        human_confirm_enabled: bool = True,
        on_confirmed: Callable[[IncidentRecord, np.ndarray], None] | None = None,
        on_pending_review: Callable[[IncidentRecord, np.ndarray], None] | None = None,
    ) -> None:
        self.config = collision_config
        self.clip_filter = clip_filter
        self.cooldown_tracker = cooldown_tracker
        self.human_confirm_enabled = human_confirm_enabled
        self.on_confirmed = on_confirmed
        self.on_pending_review = on_pending_review
        self._active: dict[str, IncidentRecord] = {}
        self._confirmed: list[IncidentRecord] = []
        self._pending: list[IncidentRecord] = []
        self._archived: list[IncidentRecord] = []
        self._last_alert_time = 0.0
        self._last_alert_location: tuple[float, float] | None = None

    @property
    def all_incidents(self) -> list[IncidentRecord]:
        return self._confirmed + self._pending + self._archived

    def process_events(self, events: list[ScoredEvent], frame: np.ndarray) -> list[IncidentRecord]:
        newly_confirmed: list[IncidentRecord] = []
        updated_keys: set[str] = set()

        if not events:
            self._decay_stale_candidates(updated_keys)
            return newly_confirmed

        for event in sorted(events, key=lambda e: e.score, reverse=True):
            if self._in_cooldown(event):
                if self.cooldown_tracker and event.location:
                    self.cooldown_tracker.record_blocked(event.location[0], event.location[1])
                continue
            key = self._event_key(event)
            record = self._active.get(key)

            if record is None:
                record = IncidentRecord(
                    id=str(uuid.uuid4()),
                    state=IncidentState.CANDIDATE,
                    event_type=event.event_type,
                    severity=event.severity,
                    score=event.score,
                    signals=list(event.signals),
                    track_ids=event.track_ids,
                    location=event.location,
                    frame_index=event.frame_index,
                    timestamp_sec=event.timestamp_sec,
                    candidate_frames=1,
                )
                self._active[key] = record
                updated_keys.add(key)
                if self._try_confirm(record, key, frame, event, newly_confirmed):
                    continue
                continue

            record.candidate_frames += 1
            record.score = max(record.score, event.score)
            record.signals = list(set(record.signals + event.signals))
            updated_keys.add(key)
            self._try_confirm(record, key, frame, event, newly_confirmed)

        self._decay_stale_candidates(updated_keys)
        return newly_confirmed

    def _try_confirm(
        self,
        record: IncidentRecord,
        key: str,
        frame: np.ndarray,
        event: ScoredEvent,
        newly_confirmed: list[IncidentRecord],
    ) -> bool:
        if record.candidate_frames < self.config.confirm_frames:
            return False

        verdict = self.clip_filter.evaluate(frame)
        record.clip_verdict = verdict
        if not verdict.accepted:
            record.state = IncidentState.DISMISSED
            del self._active[key]
            return True

        record.confirmed_at = time.time()
        self._last_alert_time = time.time()
        self._last_alert_location = event.location
        if self.cooldown_tracker and event.location:
            self.cooldown_tracker.record_alert(event.location[0], event.location[1], record.id)

        del self._active[key]

        if self.human_confirm_enabled:
            record.state = IncidentState.PENDING_REVIEW
            record.dispatch_status = "awaiting_human"
            self._pending.append(record)
            newly_confirmed.append(record)
            if self.on_pending_review:
                self.on_pending_review(record, frame)
            return True

        record.state = IncidentState.CONFIRMED
        record.dispatch_status = "pending"
        self._confirmed.append(record)
        newly_confirmed.append(record)
        if self.on_confirmed:
            self.on_confirmed(record, frame)
        return True

    def approve_pending(self, incident_id: str) -> IncidentRecord | None:
        for i, record in enumerate(self._pending):
            if record.id == incident_id:
                record.state = IncidentState.CONFIRMED
                record.dispatch_status = "pending"
                record.human_reviewed = True
                self._confirmed.append(record)
                del self._pending[i]
                return record
        return None

    def dismiss_pending(self, incident_id: str) -> IncidentRecord | None:
        for i, record in enumerate(self._pending):
            if record.id == incident_id:
                record.state = IncidentState.DISMISSED
                record.dispatch_status = "dismissed"
                record.human_reviewed = True
                del self._pending[i]
                return record
        return None

    def archive(self, incident_id: str) -> None:
        for bucket in (self._confirmed, self._pending):
            for i, record in enumerate(bucket):
                if record.id == incident_id:
                    record.state = IncidentState.ARCHIVED
                    self._archived.append(record)
                    del bucket[i]
                    return

    def _event_key(self, event: ScoredEvent) -> str:
        if event.track_ids:
            a, b = sorted(event.track_ids)
            return f"{event.event_type}:{a}:{b}"
        return f"{event.event_type}:{event.frame_index}"

    def _in_cooldown(self, event: ScoredEvent) -> bool:
        if time.time() - self._last_alert_time > self.config.cooldown_seconds:
            return False
        if self._last_alert_location is None or event.location is None:
            return True
        dist = math.hypot(
            event.location[0] - self._last_alert_location[0],
            event.location[1] - self._last_alert_location[1],
        )
        return dist < self.config.cooldown_distance_px

    def _decay_stale_candidates(self, updated_keys: set[str]) -> None:
        stale: list[str] = []
        for key, record in self._active.items():
            if key in updated_keys:
                continue
            record.candidate_frames -= 1
            if record.candidate_frames <= 0:
                stale.append(key)
        for key in stale:
            del self._active[key]

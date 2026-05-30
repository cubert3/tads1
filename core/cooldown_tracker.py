from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class CooldownZone:
    x: float
    y: float
    radius_px: float
    created_at: float
    expires_at: float
    reason: str  # "alert" | "blocked"
    incident_id: str | None = None


class CooldownTracker:
    """In-memory cooldown zones for map visualization and debouncing."""

    def __init__(self, cooldown_seconds: float, cooldown_distance_px: float) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.cooldown_distance_px = cooldown_distance_px
        self._zones: list[CooldownZone] = []

    def record_alert(self, x: float, y: float, incident_id: str) -> CooldownZone:
        now = time.time()
        zone = CooldownZone(
            x=x,
            y=y,
            radius_px=self.cooldown_distance_px,
            created_at=now,
            expires_at=now + self.cooldown_seconds,
            reason="alert",
            incident_id=incident_id,
        )
        self._zones.append(zone)
        self._prune()
        return zone

    def record_blocked(self, x: float, y: float) -> CooldownZone:
        now = time.time()
        zone = CooldownZone(
            x=x,
            y=y,
            radius_px=self.cooldown_distance_px,
            created_at=now,
            expires_at=now + self.cooldown_seconds,
            reason="blocked",
        )
        self._zones.append(zone)
        self._prune()
        return zone

    def active_zones(self) -> list[CooldownZone]:
        self._prune()
        return [z for z in self._zones if z.expires_at > time.time()]

    def _prune(self) -> None:
        now = time.time()
        self._zones = [z for z in self._zones if z.expires_at > now - 60]

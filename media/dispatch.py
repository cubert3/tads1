from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

from core.config import RoadSosConfig
from core.incident_manager import IncidentRecord

logger = logging.getLogger(__name__)


@dataclass
class DispatchEntry:
    id: str
    incident_id: str
    channel: str
    target: str
    severity: str
    action: str
    status: str
    message: str
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if self.created_at == 0.0:
            self.created_at = time.time()


class DispatchService:
    """Severity-based routing: near_miss=log, collision=police, severe=police+ambulance."""

    def __init__(self, road_sos: RoadSosConfig) -> None:
        self.road_sos = road_sos
        self.routing = road_sos.severity_routing
        self.dispatch_cfg = road_sos.dispatch

    def plan_actions(self, incident: IncidentRecord) -> list[tuple[str, str, str]]:
        """Returns list of (action, channel, target)."""
        severity = incident.severity
        if severity == "near_miss":
            route = self.routing.near_miss
        elif severity == "severe":
            route = self.routing.severe
        else:
            route = self.routing.collision

        actions: list[tuple[str, str, str]] = []
        if route in ("log_only", "log"):
            actions.append(("log", "dashboard", "incident_log"))
        if route in ("police", "police_and_ambulance"):
            if self.dispatch_cfg.police_number:
                actions.append(("notify_police", "phone", self.dispatch_cfg.police_number))
        if route in ("police_and_ambulance", "ambulance"):
            if self.dispatch_cfg.ambulance_number:
                actions.append(("notify_ambulance", "phone", self.dispatch_cfg.ambulance_number))
        if not actions:
            actions.append(("log", "dashboard", "incident_log"))
        return actions

    def build_message(self, incident: IncidentRecord) -> str:
        loc = self.road_sos.location
        plates = ", ".join(incident.plate_numbers) if incident.plate_numbers else "unknown"
        return (
            f"Road SOS | {incident.severity.upper()} | {incident.event_type} | "
            f"score={incident.score:.2f} | plates={plates} | "
            f"location={loc.latitude},{loc.longitude} ({loc.label}) | "
            f"incident={incident.id}"
        )

    async def execute(
        self,
        incident: IncidentRecord,
        webhook_url: str | None,
        on_persist: Any | None = None,
    ) -> list[DispatchEntry]:
        entries: list[DispatchEntry] = []
        message = self.build_message(incident)

        for action, channel, target in self.plan_actions(incident):
            entry = DispatchEntry(
                id=str(uuid.uuid4()),
                incident_id=incident.id,
                channel=channel,
                target=target,
                severity=incident.severity,
                action=action,
                status="queued",
                message=message,
            )
            if action == "log":
                entry.status = "logged"
            elif channel == "phone" and webhook_url:
                ok = await self._post_webhook(webhook_url, {**self._payload(incident), "dispatch": entry.__dict__})
                entry.status = "sent" if ok else "failed"
            elif channel == "phone":
                entry.status = "simulated"
            entries.append(entry)

        if on_persist:
            await on_persist(entries)
        return entries

    def _payload(self, incident: IncidentRecord) -> dict[str, Any]:
        loc = self.road_sos.location
        return {
            "id": incident.id,
            "event_type": incident.event_type,
            "severity": incident.severity,
            "score": incident.score,
            "signals": incident.signals,
            "plate_numbers": incident.plate_numbers,
            "latitude": loc.latitude,
            "longitude": loc.longitude,
            "location_label": loc.label,
            "timestamp_sec": incident.timestamp_sec,
            "clip_path": incident.clip_path,
            "dispatch_status": incident.dispatch_status,
        }

    async def _post_webhook(self, url: str, payload: dict[str, Any]) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
            return True
        except Exception as exc:
            logger.warning("Dispatch webhook failed: %s", exc)
            return False

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from core.config import AlertsConfig
from core.incident_manager import IncidentRecord

logger = logging.getLogger(__name__)


class Alerter:
    def __init__(self, config: AlertsConfig) -> None:
        self.config = config
        self._subscribers: list[asyncio.Queue] = []

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(queue)
        return queue

    async def notify(self, incident: IncidentRecord) -> None:
        payload = {
            "id": incident.id,
            "state": incident.state.value,
            "event_type": incident.event_type,
            "severity": incident.severity,
            "score": incident.score,
            "signals": incident.signals,
            "timestamp_sec": incident.timestamp_sec,
            "clip_path": incident.clip_path,
            "dispatch_status": incident.dispatch_status,
            "plate_numbers": incident.plate_numbers,
            "latitude": incident.latitude,
            "longitude": incident.longitude,
            "location_label": incident.location_label,
        }
        for queue in self._subscribers:
            await queue.put(payload)

        if self.config.webhook_url:
            await self._send_webhook(payload)

    async def _send_webhook(self, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.config.webhook_url, json=payload)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Webhook failed: %s", exc)

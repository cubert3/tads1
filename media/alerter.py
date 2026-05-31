from __future__ import annotations

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
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
            "event_type": incident.event_type,
            "severity": incident.severity,
            "score": incident.score,
            "signals": incident.signals,
            "timestamp_sec": incident.timestamp_sec,
            "clip_path": incident.clip_path,
        }
        for queue in self._subscribers:
            await queue.put(payload)

        if self.config.webhook_url:
            await self._send_webhook(payload)
        if self.config.smtp_enabled:
            await asyncio.to_thread(self._send_email, payload)

    async def _send_webhook(self, payload: dict[str, Any]) -> None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(self.config.webhook_url, json=payload)
                resp.raise_for_status()
        except Exception as exc:
            logger.warning("Webhook failed: %s", exc)

    def _send_email(self, payload: dict[str, Any]) -> None:
        cfg = self.config
        if not cfg.smtp_host or not cfg.smtp_to:
            return
        body = (
            f"TADS Alert\n\n"
            f"Severity: {payload['severity']}\n"
            f"Type: {payload['event_type']}\n"
            f"Score: {payload['score']:.2f}\n"
            f"Time: {payload['timestamp_sec']:.1f}s\n"
            f"Signals: {', '.join(payload['signals'])}\n"
            f"Clip: {payload.get('clip_path', 'N/A')}\n"
        )
        msg = MIMEText(body)
        msg["Subject"] = f"[TADS] {payload['severity'].upper()} — {payload['event_type']}"
        msg["From"] = cfg.smtp_user or cfg.smtp_to
        msg["To"] = cfg.smtp_to
        try:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=15) as server:
                server.starttls()
                if cfg.smtp_user and cfg.smtp_password:
                    server.login(cfg.smtp_user, cfg.smtp_password)
                server.send_message(msg)
        except Exception as exc:
            logger.warning("SMTP alert failed: %s", exc)

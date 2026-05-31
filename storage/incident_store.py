from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from core.incident_manager import IncidentRecord, IncidentState
from media.dispatch import DispatchEntry
from storage.database import Database


class IncidentStore:
    def __init__(self, db_path: Path) -> None:
        self.db = Database(db_path)

    async def save(self, record: IncidentRecord) -> None:
        conn = await self.db.connect()
        try:
            loc_x = record.location[0] if record.location else None
            loc_y = record.location[1] if record.location else None
            await conn.execute(
                """
                INSERT OR REPLACE INTO incidents
                (id, state, event_type, severity, score, signals, track_ids,
                 location_x, location_y, frame_index, timestamp_sec,
                 clip_path, keyframe_path, source_video, created_at, confirmed_at,
                 dispatch_status, plate_numbers, latitude, longitude, location_label, human_reviewed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.state.value,
                    record.event_type,
                    record.severity,
                    record.score,
                    json.dumps(record.signals),
                    json.dumps(record.track_ids),
                    loc_x,
                    loc_y,
                    record.frame_index,
                    record.timestamp_sec,
                    record.clip_path,
                    record.keyframe_path,
                    record.source_video,
                    record.created_at,
                    record.confirmed_at,
                    record.dispatch_status,
                    json.dumps(record.plate_numbers),
                    record.latitude,
                    record.longitude,
                    record.location_label,
                    1 if record.human_reviewed else 0,
                ),
            )
            await conn.commit()
        finally:
            await conn.close()

    async def update_state(
        self,
        incident_id: str,
        state: str,
        dispatch_status: str,
        human_reviewed: bool = True,
    ) -> bool:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute(
                """
                UPDATE incidents
                SET state = ?, dispatch_status = ?, human_reviewed = ?, confirmed_at = ?
                WHERE id = ?
                """,
                (state, dispatch_status, 1 if human_reviewed else 0, time.time(), incident_id),
            )
            await conn.commit()
            return cursor.rowcount > 0
        finally:
            await conn.close()

    async def list_since(self, since_ts: float, limit: int = 500) -> list[dict]:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute(
                """
                SELECT * FROM incidents WHERE created_at >= ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (since_ts, limit),
            )
            rows = await cursor.fetchall()
            return [self._row_to_dict(row, cursor) for row in rows]
        finally:
            await conn.close()

    async def list_all(
        self,
        severity: str | None = None,
        state: str | None = None,
    ) -> list[dict]:
        conn = await self.db.connect()
        try:
            query = "SELECT * FROM incidents WHERE 1=1"
            params: list = []
            if severity:
                query += " AND severity = ?"
                params.append(severity)
            if state:
                query += " AND state = ?"
                params.append(state)
            query += " ORDER BY created_at DESC"
            cursor = await conn.execute(query, params)
            rows = await cursor.fetchall()
            return [self._row_to_dict(row, cursor) for row in rows]
        finally:
            await conn.close()

    async def get(self, incident_id: str) -> dict | None:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
            row = await cursor.fetchone()
            if not row:
                return None
            return self._row_to_dict(row, cursor)
        finally:
            await conn.close()

    async def save_dispatch_entries(self, entries: list[DispatchEntry]) -> None:
        conn = await self.db.connect()
        try:
            for entry in entries:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO dispatch_log
                    (id, incident_id, channel, target, severity, action, status, message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.id,
                        entry.incident_id,
                        entry.channel,
                        entry.target,
                        entry.severity,
                        entry.action,
                        entry.status,
                        entry.message,
                        entry.created_at,
                    ),
                )
            await conn.commit()
        finally:
            await conn.close()

    async def list_dispatch_log(self, limit: int = 100) -> list[dict]:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute(
                "SELECT * FROM dispatch_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            await conn.close()

    async def save_cooldown_zones(self, zones: list) -> None:
        conn = await self.db.connect()
        try:
            for zone in zones:
                await conn.execute(
                    """
                    INSERT OR REPLACE INTO cooldown_zones
                    (id, x, y, radius_px, reason, incident_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        zone.x,
                        zone.y,
                        zone.radius_px,
                        zone.reason,
                        zone.incident_id,
                        zone.created_at,
                        zone.expires_at,
                    ),
                )
            await conn.commit()
        finally:
            await conn.close()

    async def list_cooldown_zones(self) -> list[dict]:
        conn = await self.db.connect()
        try:
            now = time.time()
            cursor = await conn.execute(
                "SELECT * FROM cooldown_zones WHERE expires_at > ? ORDER BY created_at DESC LIMIT 200",
                (now,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            await conn.close()

    async def analytics_summary(self) -> dict:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute(
                """
                SELECT severity, COUNT(*) as cnt
                FROM incidents
                WHERE state IN ('confirmed', 'pending_review', 'archived')
                GROUP BY severity
                """
            )
            rows = await cursor.fetchall()
            by_severity = {row[0]: row[1] for row in rows}
            cursor2 = await conn.execute("SELECT COUNT(*) FROM incidents WHERE state = 'pending_review'")
            pending = (await cursor2.fetchone())[0]
            day_start = time.time() - 86400
            cursor3 = await conn.execute(
                """
                SELECT severity, COUNT(*) FROM incidents
                WHERE created_at >= ? AND severity IN ('collision', 'near_miss', 'severe')
                GROUP BY severity
                """,
                (day_start,),
            )
            today_rows = await cursor3.fetchall()
            today_by_severity = {row[0]: row[1] for row in today_rows}
            return {
                "by_severity": by_severity,
                "pending_review": pending,
                "today_by_severity": today_by_severity,
            }
        finally:
            await conn.close()

    async def analytics_timeline(self, limit: int = 200) -> list[dict]:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute(
                """
                SELECT id, severity, event_type, score, created_at, timestamp_sec
                FROM incidents
                WHERE state IN ('confirmed', 'pending_review')
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            await conn.close()

    async def map_pins(self, limit: int = 50) -> list[dict]:
        conn = await self.db.connect()
        try:
            cursor = await conn.execute(
                """
                SELECT id, severity, latitude, longitude, location_label, created_at
                FROM incidents
                WHERE latitude IS NOT NULL AND longitude IS NOT NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]
        finally:
            await conn.close()

    def _row_to_dict(self, row, cursor) -> dict:
        cols = [d[0] for d in cursor.description]
        item = dict(zip(cols, row))
        item["signals"] = json.loads(item["signals"]) if item.get("signals") else []
        item["track_ids"] = json.loads(item["track_ids"]) if item.get("track_ids") else None
        if item.get("plate_numbers"):
            try:
                item["plate_numbers"] = json.loads(item["plate_numbers"])
            except (json.JSONDecodeError, TypeError):
                item["plate_numbers"] = []
        else:
            item["plate_numbers"] = []
        return item

    @staticmethod
    def record_from_row(item: dict) -> IncidentRecord:
        loc = None
        if item.get("location_x") is not None and item.get("location_y") is not None:
            loc = (float(item["location_x"]), float(item["location_y"]))
        track_ids = item.get("track_ids")
        if track_ids and isinstance(track_ids, list) and len(track_ids) == 2:
            track_ids = (int(track_ids[0]), int(track_ids[1]))
        else:
            track_ids = None
        return IncidentRecord(
            id=item["id"],
            state=IncidentState(item["state"]),
            event_type=item["event_type"],
            severity=item["severity"],
            score=float(item["score"]),
            signals=item.get("signals") or [],
            track_ids=track_ids,
            location=loc,
            frame_index=int(item.get("frame_index") or 0),
            timestamp_sec=float(item.get("timestamp_sec") or 0),
            clip_path=item.get("clip_path"),
            keyframe_path=item.get("keyframe_path"),
            source_video=item.get("source_video"),
            created_at=float(item.get("created_at") or 0),
            confirmed_at=item.get("confirmed_at"),
            dispatch_status=item.get("dispatch_status") or "pending",
            plate_numbers=item.get("plate_numbers") or [],
            latitude=item.get("latitude"),
            longitude=item.get("longitude"),
            location_label=item.get("location_label"),
            human_reviewed=bool(item.get("human_reviewed")),
        )

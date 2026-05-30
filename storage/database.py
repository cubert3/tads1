from __future__ import annotations

import aiosqlite
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    score REAL NOT NULL,
    signals TEXT NOT NULL,
    track_ids TEXT,
    location_x REAL,
    location_y REAL,
    frame_index INTEGER,
    timestamp_sec REAL,
    clip_path TEXT,
    keyframe_path TEXT,
    source_video TEXT,
    created_at REAL,
    confirmed_at REAL,
    dispatch_status TEXT DEFAULT 'pending',
    plate_numbers TEXT,
    latitude REAL,
    longitude REAL,
    location_label TEXT,
    human_reviewed INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dispatch_log (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    target TEXT NOT NULL,
    severity TEXT NOT NULL,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS cooldown_zones (
    id TEXT PRIMARY KEY,
    x REAL NOT NULL,
    y REAL NOT NULL,
    radius_px REAL NOT NULL,
    reason TEXT NOT NULL,
    incident_id TEXT,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL
);
"""

MIGRATIONS = [
    "ALTER TABLE incidents ADD COLUMN dispatch_status TEXT DEFAULT 'pending'",
    "ALTER TABLE incidents ADD COLUMN plate_numbers TEXT",
    "ALTER TABLE incidents ADD COLUMN latitude REAL",
    "ALTER TABLE incidents ADD COLUMN longitude REAL",
    "ALTER TABLE incidents ADD COLUMN location_label TEXT",
    "ALTER TABLE incidents ADD COLUMN human_reviewed INTEGER DEFAULT 0",
]


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def connect(self) -> aiosqlite.Connection:
        conn = await aiosqlite.connect(self.path)
        await conn.executescript(SCHEMA)
        for stmt in MIGRATIONS:
            try:
                await conn.execute(stmt)
            except aiosqlite.OperationalError:
                pass
        await conn.commit()
        return conn

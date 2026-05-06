"""SQLite-backed dispute tickets (single-node; use external DB for Cloud Run scale-out)."""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from pathlib import Path
from uuid import uuid4


def _db_path() -> str:
    return os.environ.get("DISPUTES_DB_PATH", "./data/disputes.db")


def init_disputes_db() -> None:
    path = Path(_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS disputes (
                id TEXT PRIMARY KEY,
                created_unix INTEGER NOT NULL,
                target_agent_id TEXT NOT NULL,
                verification_token TEXT,
                hiring_agent_id TEXT,
                reason TEXT NOT NULL,
                contact TEXT,
                status TEXT DEFAULT 'received',
                payload_json TEXT
            )
            """
        )


def _create_dispute_sync(
    *,
    target_agent_id: str,
    reason: str,
    verification_token: str | None,
    hiring_agent_id: str | None,
    contact: str | None,
    extra: dict | None,
) -> str:
    init_disputes_db()
    dispute_id = str(uuid4())
    created = int(time.time())
    payload = json.dumps(extra or {})
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO disputes (
              id, created_unix, target_agent_id, verification_token,
              hiring_agent_id, reason, contact, status, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'received', ?)
            """,
            (
                dispute_id,
                created,
                target_agent_id,
                verification_token,
                hiring_agent_id,
                reason,
                contact,
                payload,
            ),
        )
    return dispute_id


async def create_dispute(
    *,
    target_agent_id: str,
    reason: str,
    verification_token: str | None = None,
    hiring_agent_id: str | None = None,
    contact: str | None = None,
    extra: dict | None = None,
) -> str:
    return await asyncio.to_thread(
        _create_dispute_sync,
        target_agent_id=target_agent_id,
        reason=reason,
        verification_token=verification_token,
        hiring_agent_id=hiring_agent_id,
        contact=contact,
        extra=extra,
    )

"""SQLite persistence for agent transaction events."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from typing import Any

VALID_OUTCOMES = frozenset(
    {"success", "failure", "disputed", "refunded", "cancelled"}
)

_RATE_DENOM_OUTCOMES = frozenset({"success", "failure", "refunded"})


def _db_path() -> str:
    return os.environ.get("TRANSACTION_LOG_DB_PATH", "./data/transaction_log.db")


def _window_seconds() -> int:
    days = int(os.environ.get("LOG_AGGREGATION_WINDOW_DAYS", "90"))
    return max(1, days) * 86400


def init_db() -> None:
    import pathlib

    pathlib.Path(_db_path()).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_events (
                id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                context TEXT NOT NULL DEFAULT '',
                outcome TEXT NOT NULL,
                latency_ms INTEGER,
                metadata_json TEXT,
                created_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_time ON agent_events(agent_id, created_unix)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_ctx ON agent_events(agent_id, context, created_unix)"
        )


def insert_event(
    *,
    agent_id: str,
    outcome: str,
    context: str = "",
    latency_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    if outcome not in VALID_OUTCOMES:
        raise ValueError(f"outcome must be one of {sorted(VALID_OUTCOMES)}")
    init_db()
    eid = str(uuid.uuid4())
    now = int(time.time())
    meta = json.dumps(metadata or {})
    with sqlite3.connect(_db_path()) as conn:
        conn.execute(
            """
            INSERT INTO agent_events (
              id, agent_id, context, outcome, latency_ms, metadata_json, created_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (eid, agent_id, context or "", outcome, latency_ms, meta, now),
        )
    return eid


def aggregate_for_agent(agent_id: str, context: str | None = None) -> dict[str, Any]:
    init_db()
    cutoff = int(time.time()) - _window_seconds()
    params: list[Any] = [agent_id, cutoff]
    ctx_clause = ""
    if context:
        ctx_clause = " AND context = ?"
        params.append(context)

    with sqlite3.connect(_db_path()) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            f"""
            SELECT outcome, COUNT(*) AS c
            FROM agent_events
            WHERE agent_id = ? AND created_unix >= ? {ctx_clause}
            GROUP BY outcome
            """,
            params,
        )
        rows = {str(r["outcome"]): int(r["c"]) for r in cur}

    breakdown = {o: rows.get(o, 0) for o in sorted(VALID_OUTCOMES)}
    denom = sum(rows.get(o, 0) for o in _RATE_DENOM_OUTCOMES)
    successes = rows.get("success", 0)
    sample_size = denom
    success_rate = (successes / denom) if denom else 0.0

    return {
        "success_rate": round(success_rate, 6),
        "sample_size": sample_size,
        "window_days": _window_seconds() // 86400,
        "breakdown": breakdown,
        "agent_id": agent_id,
        "context_filter": context or None,
    }

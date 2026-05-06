"""SQLite persistence for agent identity, keys, and status."""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


def _db_path() -> str:
    return os.environ.get("IDENTITY_REGISTRY_DB_PATH", "./data/identity_registry.db")


def _require_kyc() -> bool:
    return os.environ.get("REGISTRY_REQUIRE_KYC", "").strip() in ("1", "true", "yes")


def _require_signing_key() -> bool:
    return os.environ.get("REGISTRY_REQUIRE_SIGNING_KEY", "").strip() in (
        "1",
        "true",
        "yes",
    )


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


TRUST_TIERS = frozenset({"registered", "operator_verified", "partner_attested"})


def _migrate_agents_columns(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(agents)")
    cols = {row[1] for row in cur.fetchall()}
    additions = [
        ("trust_tier", "TEXT DEFAULT 'registered'"),
        ("attested_at_unix", "INTEGER"),
        ("attestor", "TEXT"),
        ("partner_id", "TEXT"),
        ("partner_ref", "TEXT"),
    ]
    for name, decl in additions:
        if name not in cols:
            conn.execute(f"ALTER TABLE agents ADD COLUMN {name} {decl}")


def init_db() -> None:
    import pathlib

    pathlib.Path(_db_path()).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agents (
                agent_id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'active',
                org_id TEXT,
                operator_name TEXT,
                operator_contact TEXT,
                kyc_verified INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_unix INTEGER NOT NULL,
                updated_unix INTEGER NOT NULL,
                trust_tier TEXT NOT NULL DEFAULT 'registered',
                attested_at_unix INTEGER,
                attestor TEXT,
                partner_id TEXT,
                partner_ref TEXT
            )
            """
        )
        _migrate_agents_columns(conn)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_keys (
                key_id TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                public_key TEXT NOT NULL,
                algorithm TEXT NOT NULL DEFAULT 'unknown',
                created_unix INTEGER NOT NULL,
                revoked_unix INTEGER,
                FOREIGN KEY (agent_id) REFERENCES agents(agent_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_agent_keys_agent ON agent_keys(agent_id)"
        )


def _now() -> int:
    return int(time.time())


def agent_exists(agent_id: str) -> bool:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return row is not None


def register_agent(
    *,
    agent_id: str,
    org_id: str | None = None,
    operator_name: str | None = None,
    operator_contact: str | None = None,
    kyc_verified: bool = False,
    metadata: dict[str, Any] | None = None,
) -> None:
    init_db()
    now = _now()
    meta = json.dumps(metadata or {})
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agents (
              agent_id, status, org_id, operator_name, operator_contact,
              kyc_verified, metadata_json, created_unix, updated_unix, trust_tier
            ) VALUES (?, 'active', ?, ?, ?, ?, ?, ?, ?, 'registered')
            ON CONFLICT(agent_id) DO UPDATE SET
              org_id = excluded.org_id,
              operator_name = excluded.operator_name,
              operator_contact = excluded.operator_contact,
              kyc_verified = excluded.kyc_verified,
              metadata_json = excluded.metadata_json,
              updated_unix = excluded.updated_unix
            """,
            (
                agent_id,
                org_id,
                operator_name,
                operator_contact,
                1 if kyc_verified else 0,
                meta,
                now,
                now,
            ),
        )


def add_key(
    *,
    agent_id: str,
    public_key: str,
    algorithm: str = "unknown",
) -> str:
    init_db()
    key_id = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO agent_keys (key_id, agent_id, public_key, algorithm, created_unix)
            VALUES (?, ?, ?, ?, ?)
            """,
            (key_id, agent_id, public_key.strip(), algorithm, now),
        )
        conn.execute(
            "UPDATE agents SET updated_unix = ? WHERE agent_id = ?",
            (now, agent_id),
        )
    return key_id


def revoke_key(agent_id: str, key_id: str) -> bool:
    init_db()
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE agent_keys SET revoked_unix = ?
            WHERE key_id = ? AND agent_id = ? AND revoked_unix IS NULL
            """,
            (now, key_id, agent_id),
        )
        conn.execute(
            "UPDATE agents SET updated_unix = ? WHERE agent_id = ?",
            (now, agent_id),
        )
        return cur.rowcount > 0


def attest_operator(
    agent_id: str, *, attestor: str, notes: str | None = None
) -> bool:
    """Promote to operator_verified after your internal review."""
    if not agent_exists(agent_id):
        return False
    now = _now()
    with _connect() as conn:
        row = conn.execute(
            "SELECT metadata_json FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        meta: dict[str, Any] = {}
        if row and row[0]:
            try:
                meta = json.loads(row[0])
            except json.JSONDecodeError:
                meta = {}
        if notes:
            meta["operator_attest_notes"] = notes
        conn.execute(
            """
            UPDATE agents SET trust_tier = 'operator_verified', attestor = ?,
              attested_at_unix = ?, updated_unix = ?, metadata_json = ?
            WHERE agent_id = ?
            """,
            (attestor, now, now, json.dumps(meta), agent_id),
        )
    return True


def attest_partner(
    agent_id: str,
    *,
    partner_id: str,
    partner_ref: str,
    attestor: str | None = None,
) -> bool:
    """Record a B2B partner attestation (KYC vendor, marketplace, etc.)."""
    if not agent_exists(agent_id):
        return False
    now = _now()
    att = attestor or partner_id
    with _connect() as conn:
        conn.execute(
            """
            UPDATE agents SET trust_tier = 'partner_attested', partner_id = ?,
              partner_ref = ?, attestor = ?, attested_at_unix = ?, updated_unix = ?
            WHERE agent_id = ?
            """,
            (partner_id, partner_ref, att, now, now, agent_id),
        )
    return True


def set_status(agent_id: str, status: str) -> bool:
    if status not in ("active", "suspended", "revoked"):
        raise ValueError("status must be active, suspended, or revoked")
    init_db()
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE agents SET status = ?, updated_unix = ? WHERE agent_id = ?
            """,
            (status, now, agent_id),
        )
        return cur.rowcount > 0


def get_status_payload(agent_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        if not row:
            return None
        keys = conn.execute(
            """
            SELECT key_id, algorithm, created_unix, revoked_unix
            FROM agent_keys WHERE agent_id = ? ORDER BY created_unix DESC
            """,
            (agent_id,),
        ).fetchall()

    agent = dict(row)
    agent["kyc_verified"] = bool(agent["kyc_verified"])
    tt = agent.get("trust_tier") or "registered"
    if tt not in TRUST_TIERS:
        tt = "registered"
    active_keys = [dict(k) for k in keys if k["revoked_unix"] is None]
    has_live_key = len(active_keys) > 0

    st = agent["status"]
    registered = st == "active"
    if registered and _require_kyc() and not agent["kyc_verified"]:
        registered = False
    if registered and _require_signing_key() and not has_live_key:
        registered = False

    primary = active_keys[0] if active_keys else None
    return {
        "registered": registered,
        "trust_tier": tt,
        "agent_id": agent_id,
        "status": st,
        "org_id": agent["org_id"],
        "operator_name": agent["operator_name"],
        "operator_contact": agent["operator_contact"],
        "kyc_verified": agent["kyc_verified"],
        "attested_at_unix": agent.get("attested_at_unix"),
        "attestor": agent.get("attestor"),
        "partner_id": agent.get("partner_id"),
        "partner_ref": agent.get("partner_ref"),
        "primary_key": (
            {
                "key_id": primary["key_id"],
                "algorithm": primary["algorithm"],
                "created_unix": primary["created_unix"],
            }
            if primary
            else None
        ),
        "active_key_count": len(active_keys),
        "flags": _flags(agent, has_live_key, registered),
    }


def _flags(agent: dict[str, Any], has_live_key: bool, registered: bool) -> list[str]:
    flags: list[str] = []
    if agent["status"] == "suspended":
        flags.append("SUSPENDED")
    if agent["status"] == "revoked":
        flags.append("REVOKED")
    if _require_kyc() and not agent["kyc_verified"]:
        flags.append("KYC_REQUIRED")
    if _require_signing_key() and not has_live_key:
        flags.append("SIGNING_KEY_REQUIRED")
    if not registered and agent["status"] == "active" and flags:
        flags.append("NOT_ELIGIBLE")
    return flags

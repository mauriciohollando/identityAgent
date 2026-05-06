"""Persistence for Stripe adapter mandates and payer mappings."""

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
    return os.environ.get("STRIPE_ADAPTER_DB_PATH", "./data/stripe_adapter.db")


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_db_path())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _now() -> int:
    return int(time.time())


def init_db() -> None:
    import pathlib

    pathlib.Path(_db_path()).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS payer_mappings (
                payer_agent_id TEXT PRIMARY KEY,
                stripe_customer_id TEXT NOT NULL,
                stripe_payment_method_id TEXT,
                metadata_json TEXT,
                created_unix INTEGER NOT NULL,
                updated_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mandates (
                mandate_id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                payer_agent_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL,
                reason TEXT,
                stripe_payment_intent_id TEXT,
                stripe_refund_id TEXT,
                status TEXT NOT NULL,
                gateway_response_json TEXT,
                created_unix INTEGER NOT NULL,
                updated_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mandate_pi ON mandates(stripe_payment_intent_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_payer_stripe_customer "
            "ON payer_mappings(stripe_customer_id)"
        )


def upsert_payer_mapping(
    *,
    payer_agent_id: str,
    stripe_customer_id: str,
    stripe_payment_method_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    init_db()
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO payer_mappings (
              payer_agent_id, stripe_customer_id, stripe_payment_method_id,
              metadata_json, created_unix, updated_unix
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(payer_agent_id) DO UPDATE SET
              stripe_customer_id = excluded.stripe_customer_id,
              stripe_payment_method_id = excluded.stripe_payment_method_id,
              metadata_json = excluded.metadata_json,
              updated_unix = excluded.updated_unix
            """,
            (
                payer_agent_id,
                stripe_customer_id,
                stripe_payment_method_id,
                json.dumps(metadata or {}),
                now,
                now,
            ),
        )


def get_payer_mapping(payer_agent_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM payer_mappings WHERE payer_agent_id = ?",
            (payer_agent_id,),
        ).fetchone()
        return dict(row) if row else None


def find_payer_by_stripe_customer_id(stripe_customer_id: str) -> dict[str, Any] | None:
    """First payer mapping for a Stripe customer (for subscription webhooks)."""
    if not stripe_customer_id:
        return None
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM payer_mappings
            WHERE stripe_customer_id = ?
            ORDER BY updated_unix DESC
            LIMIT 1
            """,
            (stripe_customer_id,),
        ).fetchone()
        return dict(row) if row else None


def get_mandate_by_idempotency(idempotency_key: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM mandates WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return dict(row) if row else None


def create_mandate(
    *,
    idempotency_key: str,
    payer_agent_id: str,
    amount_cents: int,
    currency: str,
    reason: str,
    status: str,
    stripe_payment_intent_id: str | None = None,
    gateway_response: dict[str, Any] | None = None,
) -> str:
    init_db()
    now = _now()
    mid = f"mandate_{uuid.uuid4().hex[:20]}"
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mandates (
              mandate_id, idempotency_key, payer_agent_id, amount_cents, currency, reason,
              stripe_payment_intent_id, status, gateway_response_json, created_unix, updated_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mid,
                idempotency_key,
                payer_agent_id,
                amount_cents,
                currency.upper(),
                reason,
                stripe_payment_intent_id,
                status,
                json.dumps(gateway_response or {}),
                now,
                now,
            ),
        )
    return mid


def update_mandate(
    mandate_id: str,
    *,
    status: str,
    stripe_payment_intent_id: str | None = None,
    stripe_refund_id: str | None = None,
    gateway_response: dict[str, Any] | None = None,
) -> None:
    init_db()
    now = _now()
    sets = ["status = ?", "updated_unix = ?"]
    params: list[Any] = [status, now]
    if stripe_payment_intent_id is not None:
        sets.append("stripe_payment_intent_id = ?")
        params.append(stripe_payment_intent_id)
    if stripe_refund_id is not None:
        sets.append("stripe_refund_id = ?")
        params.append(stripe_refund_id)
    if gateway_response is not None:
        sets.append("gateway_response_json = ?")
        params.append(json.dumps(gateway_response))
    params.append(mandate_id)
    with _connect() as conn:
        conn.execute(
            f"UPDATE mandates SET {', '.join(sets)} WHERE mandate_id = ?",
            params,
        )


def find_mandate_by_pi(pi_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM mandates WHERE stripe_payment_intent_id = ?",
            (pi_id,),
        ).fetchone()
        return dict(row) if row else None


def get_mandate(mandate_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM mandates WHERE mandate_id = ?",
            (mandate_id,),
        ).fetchone()
        return dict(row) if row else None

"""SQLite ledger for payment mandates, credits, subscriptions, and audit events."""

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
    return os.environ.get("PAYMENT_LEDGER_DB_PATH", "./data/payment_ledger.db")


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


def init_payment_db() -> None:
    import pathlib

    pathlib.Path(_db_path()).parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mandates (
                id TEXT PRIMARY KEY,
                idempotency_key TEXT NOT NULL UNIQUE,
                hiring_agent_id TEXT NOT NULL,
                amount_cents INTEGER NOT NULL,
                currency TEXT NOT NULL DEFAULT 'USD',
                reason TEXT,
                status TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'gateway',
                gateway_mandate_id TEXT,
                last_error TEXT,
                gateway_response_json TEXT,
                created_unix INTEGER NOT NULL,
                updated_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mandates_gateway ON mandates(gateway_mandate_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_mandates_created ON mandates(created_unix)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credit_balances (
                hiring_agent_id TEXT PRIMARY KEY,
                balance_cents INTEGER NOT NULL DEFAULT 0,
                updated_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                reference_id TEXT,
                hiring_agent_id TEXT,
                amount_cents INTEGER,
                meta_json TEXT,
                created_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS subscription_entitlements (
                hiring_agent_id TEXT PRIMARY KEY,
                tier_id TEXT NOT NULL,
                status TEXT NOT NULL,
                included_calls INTEGER NOT NULL,
                used_calls INTEGER NOT NULL DEFAULT 0,
                period_start_unix INTEGER NOT NULL,
                period_end_unix INTEGER NOT NULL,
                metadata_json TEXT,
                updated_unix INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_subscription_period
            ON subscription_entitlements(period_end_unix, status)
            """
        )


def _now() -> int:
    return int(time.time())


def _log_event(
    event_type: str,
    *,
    reference_id: str | None = None,
    hiring_agent_id: str | None = None,
    amount_cents: int | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    init_payment_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ledger_events (
              id, event_type, reference_id, hiring_agent_id, amount_cents, meta_json, created_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                event_type,
                reference_id,
                hiring_agent_id,
                amount_cents,
                json.dumps(meta or {}),
                _now(),
            ),
        )


def find_authorized_by_idempotency(idempotency_key: str) -> dict[str, Any] | None:
    init_payment_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT * FROM mandates
            WHERE idempotency_key = ? AND status = 'authorized'
            """,
            (idempotency_key,),
        ).fetchone()
        return dict(row) if row else None


def insert_mandate(
    *,
    idempotency_key: str,
    hiring_agent_id: str,
    amount_cents: int,
    currency: str,
    reason: str,
    status: str,
    source: str,
    gateway_mandate_id: str | None = None,
    last_error: str | None = None,
    gateway_response_json: str | None = None,
) -> str:
    init_payment_db()
    mid = str(uuid.uuid4())
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mandates (
              id, idempotency_key, hiring_agent_id, amount_cents, currency, reason,
              status, source, gateway_mandate_id, last_error, gateway_response_json,
              created_unix, updated_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mid,
                idempotency_key,
                hiring_agent_id,
                amount_cents,
                currency,
                reason,
                status,
                source,
                gateway_mandate_id,
                last_error,
                gateway_response_json,
                now,
                now,
            ),
        )
    _log_event(
        "mandate_created",
        reference_id=mid,
        hiring_agent_id=hiring_agent_id,
        amount_cents=amount_cents,
        meta={"status": status, "source": source},
    )
    return mid


def update_mandate(
    mandate_row_id: str,
    *,
    status: str,
    gateway_mandate_id: str | None = None,
    last_error: str | None = None,
    gateway_response_json: str | None = None,
) -> None:
    init_payment_db()
    now = _now()
    with _connect() as conn:
        sets = ["status = ?", "updated_unix = ?"]
        params: list[Any] = [status, now]
        if gateway_mandate_id is not None:
            sets.append("gateway_mandate_id = ?")
            params.append(gateway_mandate_id)
        if last_error is not None:
            sets.append("last_error = ?")
            params.append(last_error)
        if gateway_response_json is not None:
            sets.append("gateway_response_json = ?")
            params.append(gateway_response_json)
        params.append(mandate_row_id)
        conn.execute(
            f"UPDATE mandates SET {', '.join(sets)} WHERE id = ?",
            params,
        )
    _log_event(
        "mandate_updated",
        reference_id=mandate_row_id,
        meta={"status": status},
    )


def update_mandate_by_gateway_id(
    gateway_mandate_id: str,
    *,
    status: str,
    meta: dict[str, Any] | None = None,
) -> bool:
    init_payment_db()
    now = _now()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE mandates SET status = ?, updated_unix = ?, gateway_response_json = ?
            WHERE gateway_mandate_id = ?
            """,
            (
                status,
                now,
                json.dumps(meta or {}),
                gateway_mandate_id,
            ),
        )
        return cur.rowcount > 0


def get_credit_balance(hiring_agent_id: str) -> int:
    init_payment_db()
    with _connect() as conn:
        row = conn.execute(
            "SELECT balance_cents FROM credit_balances WHERE hiring_agent_id = ?",
            (hiring_agent_id,),
        ).fetchone()
        return int(row[0]) if row else 0


def add_credits(hiring_agent_id: str, cents: int, *, note: str | None = None) -> int:
    if cents <= 0:
        raise ValueError("cents must be positive")
    init_payment_db()
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO credit_balances (hiring_agent_id, balance_cents, updated_unix)
            VALUES (?, ?, ?)
            ON CONFLICT(hiring_agent_id) DO UPDATE SET
              balance_cents = balance_cents + excluded.balance_cents,
              updated_unix = excluded.updated_unix
            """,
            (hiring_agent_id, cents, now),
        )
        row = conn.execute(
            "SELECT balance_cents FROM credit_balances WHERE hiring_agent_id = ?",
            (hiring_agent_id,),
        ).fetchone()
        new_bal = int(row[0])
    _log_event(
        "credits_added",
        hiring_agent_id=hiring_agent_id,
        amount_cents=cents,
        meta={"note": note, "balance_after": new_bal},
    )
    return new_bal


def try_debit_credits(hiring_agent_id: str, cents: int) -> bool:
    if cents <= 0:
        return False
    init_payment_db()
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO credit_balances (hiring_agent_id, balance_cents, updated_unix)
            VALUES (?, 0, ?)
            ON CONFLICT(hiring_agent_id) DO NOTHING
            """,
            (hiring_agent_id, now),
        )
        cur = conn.execute(
            """
            UPDATE credit_balances
            SET balance_cents = balance_cents - ?,
                updated_unix = ?
            WHERE hiring_agent_id = ? AND balance_cents >= ?
            """,
            (cents, now, hiring_agent_id, cents),
        )
        ok = cur.rowcount > 0
    if ok:
        _log_event(
            "credits_debited",
            hiring_agent_id=hiring_agent_id,
            amount_cents=cents,
        )
    return ok


def summary(from_unix: int, to_unix: int) -> dict[str, Any]:
    init_payment_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT status, COUNT(*) AS c, COALESCE(SUM(amount_cents), 0) AS cents
            FROM mandates
            WHERE created_unix >= ? AND created_unix <= ?
            GROUP BY status
            """,
            (from_unix, to_unix),
        ).fetchall()
    by_status = {str(r[0]): {"count": int(r[1]), "amount_cents": int(r[2])} for r in rows}
    return {"from_unix": from_unix, "to_unix": to_unix, "mandates": by_status}


def upsert_subscription_entitlement(
    *,
    hiring_agent_id: str,
    tier_id: str,
    included_calls: int,
    period_start_unix: int,
    period_end_unix: int,
    status: str = "active",
    used_calls: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not hiring_agent_id:
        raise ValueError("hiring_agent_id is required")
    if included_calls < 0:
        raise ValueError("included_calls must be >= 0")
    if used_calls < 0:
        raise ValueError("used_calls must be >= 0")
    if period_end_unix <= period_start_unix:
        raise ValueError("period_end_unix must be > period_start_unix")
    init_payment_db()
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO subscription_entitlements (
                hiring_agent_id, tier_id, status, included_calls, used_calls,
                period_start_unix, period_end_unix, metadata_json, updated_unix
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hiring_agent_id) DO UPDATE SET
                tier_id = excluded.tier_id,
                status = excluded.status,
                included_calls = excluded.included_calls,
                used_calls = excluded.used_calls,
                period_start_unix = excluded.period_start_unix,
                period_end_unix = excluded.period_end_unix,
                metadata_json = excluded.metadata_json,
                updated_unix = excluded.updated_unix
            """,
            (
                hiring_agent_id,
                tier_id,
                status,
                included_calls,
                used_calls,
                period_start_unix,
                period_end_unix,
                json.dumps(metadata or {}),
                now,
            ),
        )
    _log_event(
        "subscription_upserted",
        hiring_agent_id=hiring_agent_id,
        meta={
            "tier_id": tier_id,
            "status": status,
            "included_calls": included_calls,
            "used_calls": used_calls,
            "period_start_unix": period_start_unix,
            "period_end_unix": period_end_unix,
        },
    )


def get_subscription_entitlement(hiring_agent_id: str) -> dict[str, Any] | None:
    init_payment_db()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT hiring_agent_id, tier_id, status, included_calls, used_calls,
                   period_start_unix, period_end_unix, metadata_json, updated_unix
            FROM subscription_entitlements
            WHERE hiring_agent_id = ?
            """,
            (hiring_agent_id,),
        ).fetchone()
    if not row:
        return None
    out = dict(row)
    try:
        out["metadata"] = json.loads(out.pop("metadata_json") or "{}")
    except json.JSONDecodeError:
        out["metadata"] = {}
    remaining = max(0, int(out["included_calls"]) - int(out["used_calls"]))
    out["remaining_calls"] = remaining
    return out


def consume_subscription_call(hiring_agent_id: str) -> dict[str, Any]:
    """Atomically consume one call if entitlement is active and in period."""
    init_payment_db()
    now = _now()
    with _connect() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT hiring_agent_id, tier_id, status, included_calls, used_calls,
                   period_start_unix, period_end_unix
            FROM subscription_entitlements
            WHERE hiring_agent_id = ?
            """,
            (hiring_agent_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "reason": "no_entitlement"}
        rec = dict(row)
        if str(rec["status"]).lower() != "active":
            return {"ok": False, "reason": "inactive"}
        if now < int(rec["period_start_unix"]) or now >= int(rec["period_end_unix"]):
            return {"ok": False, "reason": "outside_period"}
        included = int(rec["included_calls"])
        used = int(rec["used_calls"])
        if used >= included:
            return {"ok": False, "reason": "quota_exhausted"}
        cur = conn.execute(
            """
            UPDATE subscription_entitlements
            SET used_calls = used_calls + 1, updated_unix = ?
            WHERE hiring_agent_id = ? AND used_calls < included_calls
            """,
            (now, hiring_agent_id),
        )
        if cur.rowcount == 0:
            return {"ok": False, "reason": "quota_exhausted"}
    remaining_after = max(0, included - (used + 1))
    _log_event(
        "subscription_call_consumed",
        hiring_agent_id=hiring_agent_id,
        meta={"tier_id": rec["tier_id"], "remaining_calls": remaining_after},
    )
    return {
        "ok": True,
        "tier_id": rec["tier_id"],
        "included_calls": included,
        "used_calls": used + 1,
        "remaining_calls": remaining_after,
        "period_end_unix": int(rec["period_end_unix"]),
    }

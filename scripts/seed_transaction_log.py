#!/usr/bin/env python3
"""Insert sample events into the transaction log (requires log service DB path)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    sys.path.insert(0, str(src))

    parser = argparse.ArgumentParser()
    parser.add_argument("agent_id")
    parser.add_argument("--context", default="demo")
    parser.add_argument("--success", type=int, default=8)
    parser.add_argument("--failure", type=int, default=2)
    args = parser.parse_args()

    import os

    os.environ.setdefault("TRANSACTION_LOG_DB_PATH", str(root / "data/transaction_log.db"))

    from transaction_log.store import init_db
    from transaction_log.store import insert_event

    init_db()
    for _ in range(args.success):
        insert_event(
            agent_id=args.agent_id,
            outcome="success",
            context=args.context,
        )
    for _ in range(args.failure):
        insert_event(
            agent_id=args.agent_id,
            outcome="failure",
            context=args.context,
        )
    print(f"Seeded {args.success} success, {args.failure} failure for {args.agent_id!r}")


if __name__ == "__main__":
    main()

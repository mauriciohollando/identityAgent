#!/usr/bin/env python3
"""Run identity + reputation checks without uvicorn or GOOGLE_API_KEY."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path


def _ensure_src_path() -> None:
    root = Path(__file__).resolve().parent.parent
    src = root / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))


async def _main() -> None:
    _ensure_src_path()
    import auditor

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("agent_id", help="Target agent id to audit")
    parser.add_argument(
        "--context",
        default="smoke-test",
        help="Context string passed to performance history",
    )
    args = parser.parse_args()

    identity = await auditor.verify_identity(args.agent_id)
    audit = await auditor.audit_reputation(args.agent_id, args.context)
    print(json.dumps({"identity": identity, "audit": audit}, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())

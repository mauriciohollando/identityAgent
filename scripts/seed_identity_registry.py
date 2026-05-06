#!/usr/bin/env python3
"""Register a demo agent in the local identity registry SQLite DB."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "src"))

    parser = argparse.ArgumentParser()
    parser.add_argument("agent_id")
    parser.add_argument("--org", default="demo-org")
    parser.add_argument("--operator", default="Demo Operator")
    parser.add_argument("--contact", default="ops@example.com")
    parser.add_argument("--kyc", action="store_true")
    parser.add_argument("--public-key", dest="public_key", default="demo-public-key-material")
    args = parser.parse_args()

    import os

    os.environ.setdefault(
        "IDENTITY_REGISTRY_DB_PATH", str(root / "data/identity_registry.db")
    )

    from identity_registry.store import add_key
    from identity_registry.store import get_status_payload
    from identity_registry.store import init_db
    from identity_registry.store import register_agent

    init_db()
    register_agent(
        agent_id=args.agent_id,
        org_id=args.org,
        operator_name=args.operator,
        operator_contact=args.contact,
        kyc_verified=args.kyc,
        metadata={"source": "seed_identity_registry.py"},
    )
    add_key(agent_id=args.agent_id, public_key=args.public_key, algorithm="seed")
    print(json.dumps(get_status_payload(args.agent_id), indent=2))


if __name__ == "__main__":
    main()

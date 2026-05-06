"""HMAC-signed opaque verification tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time


def generate_signed_token(target_agent_id: str, ttl_seconds: int = 3600) -> str:
    """Return url-safe token binding *target_agent_id* and expiry to ``AUDITOR_TOKEN_SECRET``."""
    secret = os.environ.get("AUDITOR_TOKEN_SECRET", "dev-insecure-secret")
    issued = int(time.time())
    expiry = issued + ttl_seconds
    payload = f"{target_agent_id}:{issued}:{expiry}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).digest()
    body = base64.urlsafe_b64encode(payload + b"." + sig).decode("ascii").rstrip("=")
    return f"v1.{body}"

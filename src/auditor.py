"""Trust Auditor — ADK agent exposed over A2A with AP2 payment interceptors."""

from __future__ import annotations

import hashlib
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryPushNotificationConfigStore
from a2a.server.tasks import InMemoryTaskStore
from a2a.server.agent_execution.context import RequestContext
from a2a.types import AgentCard
from a2a.types import InvalidRequestError
from a2a.utils.errors import ServerError
from google.adk.agents import Agent
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig
from google.adk.a2a.executor.config import ExecuteInterceptor
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.tools.function_tool import FunctionTool
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from audit_regimes.anti_abuse import collect_identity_warnings
from audit_regimes.anti_abuse import collect_performance_warnings
from audit_regimes.anti_abuse import tier_sample_warnings
from audit_regimes.identity import verify_identity_full
from audit_regimes.performance import get_performance_history
from audit_regimes.tokens import generate_signed_token
from config import DISPUTE_FILING_URL
from evidence import build_evidence
from middleware.rate_limit import RateLimitMiddleware
from observability.metrics import inc_identity_check
from observability.metrics import inc_verification
from observability.metrics import render_prometheus
from payment_routes import payment_internal_routes
from payment_store import init_payment_db
from payments import handle_payment_handshake
from tiers import resolve_tier

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_CARD_PATH = PROJECT_ROOT / ".well-known" / "agent-card.json"


def _public_rpc_url() -> str:
    base = os.environ.get("AGENT_PUBLIC_BASE_URL", "").strip()
    if base:
        return base.rstrip("/") + "/"
    port = int(os.environ.get("PORT", "8080"))
    return f"http://127.0.0.1:{port}/"


def _load_agent_card_with_public_url() -> AgentCard:
    raw = json.loads(AGENT_CARD_PATH.read_text(encoding="utf-8"))
    raw["url"] = _public_rpc_url()
    return AgentCard.model_validate(raw)


def _payment_idempotency_key(context: RequestContext, hiring_agent_id: str) -> str:
    tid = context.task_id or ""
    cid = context.context_id or ""
    mid = ""
    if context.message:
        mid = context.message.message_id or ""
    raw = f"{tid}|{cid}|{mid}|{hiring_agent_id}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def _payment_before_agent(context: RequestContext) -> RequestContext:
    hiring: str | None = None
    if context.message and context.message.metadata:
        meta = context.message.metadata
        hiring = meta.get("hiringAgentId") or meta.get("hiring_agent_id")
    if hiring is None:
        hiring = context.metadata.get("hiringAgentId") or context.metadata.get(
            "hiring_agent_id"
        )
    hiring = hiring or "anonymous"
    idem = _payment_idempotency_key(context, hiring)
    if not await handle_payment_handshake(hiring, idempotency_key=idem):
        raise ServerError(
            InvalidRequestError(
                message="AP2 verification fee was not authorized for this request."
            )
        )
    return context


async def _healthz(_: Any) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "trust_auditor_a2a"})


async def _metrics_http(_: Any) -> PlainTextResponse:
    return PlainTextResponse(
        render_prometheus(), media_type="text/plain; version=0.0.4; charset=utf-8"
    )


async def verify_identity(
    target_agent_id: str, verification_tier: str | None = None
) -> dict[str, Any]:
    """Run identity checks; includes structured ``evidence`` for SLAs and disputes."""
    tier = resolve_tier(verification_tier)
    id_full = await verify_identity_full(target_agent_id)
    warnings = collect_identity_warnings(id_full)
    placeholder_perf: dict[str, Any] = {
        "success_rate": None,
        "sample_size": 0,
        "sources": [],
        "aggregation": "n/a",
        "high_disagreement": False,
    }
    evidence = build_evidence(
        tier=tier,
        identity=id_full,
        performance=placeholder_perf,
        warnings=warnings,
        trust_score=0.0,
        status="IDENTITY_ONLY",
        anti_abuse_notes=[],
    )
    inc_identity_check()
    return {
        "target_agent_id": target_agent_id,
        "identity_valid": id_full.get("valid"),
        "tier": tier.name,
        "warnings": warnings,
        "evidence": evidence,
        "dispute_filing_url": DISPUTE_FILING_URL or None,
    }


async def audit_reputation(
    target_agent_id: str,
    context: str = "",
    verification_tier: str | None = None,
) -> dict[str, Any]:
    """Full trust score with multi-source performance, tier rules, and evidence."""
    tier = resolve_tier(verification_tier)
    id_full = await verify_identity_full(target_agent_id)
    perf = await get_performance_history(target_agent_id, context)

    warnings: list[str] = []
    warnings.extend(collect_identity_warnings(id_full))
    warnings.extend(collect_performance_warnings(perf))
    warnings.extend(tier_sample_warnings(perf, tier))

    trust_score = round(
        (float(id_full["valid"]) * 0.4 + float(perf["success_rate"]) * 0.6) * 100,
        2,
    )
    status = "APPROVED" if trust_score > 75 else "FLAGGED"
    if "INSUFFICIENT_SAMPLE_FOR_TIER" in warnings:
        status = "REVIEW_REQUIRED"
    elif "HIGH_SOURCE_DISAGREEMENT" in warnings:
        status = "REVIEW_REQUIRED"
    elif "ENTERPRISE_REQUIRES_LIVE_MCP" in warnings:
        status = "REVIEW_REQUIRED"
    elif "STUB_PERFORMANCE_DATA" in warnings:
        status = "REVIEW_REQUIRED"
    elif "NO_PERFORMANCE_DATA" in warnings:
        status = "REVIEW_REQUIRED"

    notes = [w for w in warnings if w not in ("IDENTITY_SOURCE_ERROR",)]

    evidence = build_evidence(
        tier=tier,
        identity=id_full,
        performance=perf,
        warnings=warnings,
        trust_score=trust_score,
        status=status,
        anti_abuse_notes=notes,
    )
    inc_verification()
    token = generate_signed_token(target_agent_id)
    return {
        "trust_score": trust_score,
        "verification_token": token,
        "status": status,
        "identity_valid": id_full.get("valid"),
        "performance": perf,
        "tier": tier.name,
        "warnings": sorted(set(warnings)),
        "evidence": evidence,
        "dispute_filing_url": DISPUTE_FILING_URL or None,
    }


root_agent = Agent(
    model=os.environ.get("AUDITOR_LLM_MODEL", "gemini-2.5-flash"),
    name="trust_auditor",
    instruction=(
        "You are TrustAuditor, an A2A trust-layer agent. "
        "For identity-only requests, call verify_identity with the target agent id "
        "and optional verification_tier: 'standard' or 'enterprise'. "
        "For full reputation scoring, call audit_reputation with the target agent id, "
        "a short context string (domain or transaction type), and optional verification_tier. "
        "Summarize tool JSON (trust_score, status, warnings, evidence) clearly for the caller."
    ),
    tools=[
        FunctionTool(verify_identity),
        FunctionTool(audit_reputation),
    ],
)


async def _create_runner() -> Runner:
    return Runner(
        app_name=root_agent.name or "trust_auditor",
        agent=root_agent,
        artifact_service=InMemoryArtifactService(),
        session_service=InMemorySessionService(),
        memory_service=InMemoryMemoryService(),
        credential_service=InMemoryCredentialService(),
    )


def build_a2a_app() -> Starlette:
    """Starlette app with A2A routes, payment middleware, health, and metrics."""
    adk_logger = logging.getLogger("google_adk")
    adk_logger.setLevel(logging.INFO)

    task_store = InMemoryTaskStore()
    executor_config = A2aAgentExecutorConfig(
        execute_interceptors=[
            ExecuteInterceptor(before_agent=_payment_before_agent),
        ]
    )
    agent_executor = A2aAgentExecutor(
        runner=_create_runner,
        config=executor_config,
    )
    push_config_store = InMemoryPushNotificationConfigStore()
    request_handler = DefaultRequestHandler(
        agent_executor=agent_executor,
        task_store=task_store,
        push_config_store=push_config_store,
    )

    card_builder = AgentCardBuilder(
        agent=root_agent,
        rpc_url=_public_rpc_url(),
    )

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        init_payment_db()
        try:
            final_card = _load_agent_card_with_public_url()
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("Falling back to generated agent card: %s", exc)
            final_card = await card_builder.build()

        a2a = A2AStarletteApplication(
            agent_card=final_card,
            http_handler=request_handler,
        )
        a2a.add_routes_to_app(app)
        yield

    base_routes = [
        # Keep both common probe paths to simplify Cloud Run/LB health checks.
        Route("/healthz", _healthz, methods=["GET"]),
        Route("/health", _healthz, methods=["GET"]),
        Route("/internal/healthz", _healthz, methods=["GET"]),
        Route("/metrics", _metrics_http, methods=["GET"]),
        *payment_internal_routes(),
    ]

    return Starlette(
        routes=base_routes,
        lifespan=lifespan,
        middleware=[Middleware(RateLimitMiddleware)],
    )


a2a_app = build_a2a_app()

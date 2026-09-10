"""
FastAPI app factory. Builds every process-lifetime singleton (Mongo connection, agent graph,
LLM provider, GPS client, KB collection) once at startup and stores them on `app.state` —
app/api/deps.py's `get_db`/`get_graph` read from there, which is what makes them overridable in
tests via `app.dependency_overrides` without needing a second app-construction code path.
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agent.graph import build_graph
from app.api.routers import auth, chat, health, usage
from app.core.config import settings
from app.core.logging import configure_logging, request_id_var, session_id_var
from app.db.client import get_database
from app.db.repositories.llm_usage_repository import LLMUsageRepository
from app.db.repositories.session_repository import SessionRepository
from app.kb.chroma_client import get_kb_collection
from app.llm.factory import get_llm_provider
from app.llm.providers.bedrock import BedrockProvider
from app.llm.usage_tracking import TrackingLLMProvider
from app.memory.checkpointer import get_checkpointer
from app.nlu.intent_classifier import get_intent_classifier
from app.tools.fleet_gps_client import MockFleetGPSClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    db = get_database()
    app.state.db = db
    # Wrapped once here, not inside get_llm_provider() itself (which is @lru_cache'd and has
    # no db to hand a repository to) — passed into both get_intent_classifier() and
    # build_graph() so intent classification (when LLM_PROVIDER strategy is "llm") and every
    # other real LLM call are tracked through the identical wrapper instance.
    llm_provider = get_llm_provider()
    tracked_llm = TrackingLLMProvider(llm_provider, LLMUsageRepository(db), provider_name=settings.llm_provider)

    # Credential pre-flight, logged loudly but non-fatal: get_llm_provider() never raises by
    # design (see its own docstring — a misconfigured LLM provider must not block every other
    # route), so a bad Bedrock credential setup would otherwise stay silent until the first real
    # chat message needs one, possibly hours later. This surfaces it immediately in the startup
    # logs instead. For an actual hard-fail check (CI/pre-deploy), use
    # `python -m app.llm.providers.bedrock` instead — deliberately not what happens here.
    if isinstance(llm_provider, BedrockProvider):
        try:
            await llm_provider.verify_credentials()
            logger.info("Bedrock credentials verified at startup (profile=%s)", settings.aws_profile or "default chain")
        except Exception:
            logger.error(
                "Bedrock credentials could NOT be resolved at startup (profile=%r, region=%s) — "
                "real LLM calls will fail until this is fixed. Run "
                "`python -m app.llm.providers.bedrock` for a standalone check.",
                settings.aws_profile,
                settings.bedrock_region,
                exc_info=True,
            )
    app.state.graph = build_graph(
        classifier=get_intent_classifier(llm=tracked_llm),
        db=db,
        llm=tracked_llm,
        gps_client=MockFleetGPSClient(),
        kb_collection=get_kb_collection(),
        session_repo=SessionRepository(db),
        checkpointer=get_checkpointer(),
    )
    logger.info("startup complete")
    yield
    logger.info("shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="Track91 Fleet Chatbot", lifespan=lifespan)

    # Permissive dev-only CORS so a standalone local HTML test page (file:// or a different
    # localhost port) can call this API from the browser. Tighten to explicit origins before
    # any real deployment (Phase 13) — not addressed here since that phase is on hold.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        session_id_var.set(None)
        start = time.monotonic()

        logger.info("request started", extra={"method": request.method, "path": request.url.path})
        response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={"method": request.method, "path": request.url.path, "status_code": response.status_code, "duration_ms": duration_ms},
        )
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled exception")
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(chat.router)
    app.include_router(usage.router)

    return app


app = create_app()

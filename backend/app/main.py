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
from fastapi.responses import JSONResponse

from app.agent.graph import build_graph
from app.api.routers import auth, chat, health
from app.core.config import settings
from app.core.logging import configure_logging, request_id_var, session_id_var
from app.db.client import get_database
from app.db.repositories.session_repository import SessionRepository
from app.kb.chroma_client import get_kb_collection
from app.llm.factory import get_llm_provider
from app.memory.checkpointer import get_checkpointer
from app.nlu.intent_classifier import get_intent_classifier
from app.tools.fleet_gps_client import MockFleetGPSClient

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(settings.log_level)

    db = get_database()
    app.state.db = db
    app.state.graph = build_graph(
        classifier=get_intent_classifier(),
        db=db,
        llm=get_llm_provider(),
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

    return app


app = create_app()

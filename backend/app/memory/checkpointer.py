"""
LangGraph checkpointer wiring — ADR 005
(docs/phase-2-architecture/adr/005-langgraph-fastapi-boundary.md): LangGraph's own checkpointer
persists graph state between calls, keyed by session_id (LangGraph's "thread_id"). Phase 10
will build the actual graph; this phase only has to make a working, expiring checkpointer
available for it to compile with.

Uses the official `langgraph-checkpoint-mongodb` package rather than a hand-rolled one —
correctly implementing LangGraph's checkpoint serialization protocol is non-trivial, and this is
the maintained, official integration. Its constructor takes a sync `pymongo.MongoClient`, which
is a library-internal detail, not a violation of "motor everywhere" (ADR 001's "only repository
modules import motor" rule): every call site in this codebase uses the saver's *async* methods
(`aget_tuple`/`aput`/`alist`/...), which the library itself dispatches through a thread executor
so the event loop is never blocked. This is the one deliberate, narrowly-scoped exception to
that rule, made because LangGraph's official MongoDB integration doesn't ship a motor-native
client in the installed version (0.4.0).
"""

from functools import lru_cache

from langgraph.checkpoint.mongodb.saver import MongoDBSaver
from pymongo import MongoClient

from app.core.config import settings

CHECKPOINT_COLLECTION_NAME = "langgraph_checkpoints"
WRITES_COLLECTION_NAME = "langgraph_checkpoint_writes"


@lru_cache
def get_checkpointer() -> MongoDBSaver:
    client = MongoClient(settings.mongo_uri)
    return MongoDBSaver(
        client,
        db_name=settings.mongo_db_name,
        checkpoint_collection_name=CHECKPOINT_COLLECTION_NAME,
        writes_collection_name=WRITES_COLLECTION_NAME,
        # Same expiry window as chat_sessions (settings.session_ttl_seconds) — checkpoint state
        # and our own session record represent the same conversation and should expire together.
        ttl=settings.session_ttl_seconds,
    )

"""
Standalone ingestion CLI: kb_sources/**/*.md -> chunk -> embed -> ChromaDB upsert (+ Mongo
documents_meta sync). Deliberately NOT part of the API request path — per the roadmap,
chunking/embedding happens offline as a batch job; the chat request path (Phase 7+) only ever
queries the already-populated ChromaDB collection.

Idempotent: chunk IDs are stable (chunker.py), and a chunk is only re-embedded if its
content_hash changed since the last run — an unchanged source file re-ingests as a no-op rather
than creating duplicates.

Usage: python -m app.kb.ingest
"""

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from chromadb.api.models.Collection import Collection
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import settings
from app.db.client import get_database
from app.kb.chroma_client import get_kb_collection
from app.kb.chunker import Chunk, load_and_chunk_source_dir
from app.kb.embedder import embed_texts

logger = logging.getLogger(__name__)


def _existing_content_hashes(collection: Collection) -> dict[str, str]:
    existing = collection.get()
    return dict(zip(existing["ids"], (m.get("content_hash") for m in existing["metadatas"])))


def ingest_chunks(chunks: list[Chunk], collection: Collection | None = None) -> dict:
    collection = collection if collection is not None else get_kb_collection()
    existing_hashes = _existing_content_hashes(collection)

    to_embed = [c for c in chunks if existing_hashes.get(c.chunk_id) != c.content_hash]
    skipped = len(chunks) - len(to_embed)

    if to_embed:
        vectors = embed_texts([c.text for c in to_embed])
        collection.upsert(
            ids=[c.chunk_id for c in to_embed],
            embeddings=vectors,
            documents=[c.text for c in to_embed],
            metadatas=[
                {
                    "doc_id": c.doc_id,
                    "title": c.title,
                    "category": c.category,
                    "section_title": c.section_title,
                    "doc_version": c.doc_version,
                    "approved_pricing": c.approved_pricing,
                    "chunk_index": c.chunk_index,
                    "content_hash": c.content_hash,
                    "source_path": c.source_path,
                }
                for c in to_embed
            ],
        )

    return {
        "total_chunks": len(chunks),
        "embedded": len(to_embed),
        "skipped_unchanged": skipped,
        "collection_count": collection.count(),
    }


async def sync_documents_meta(chunks: list[Chunk], db: AsyncIOMotorDatabase | None = None) -> None:
    """Keep Mongo's documents_meta (doc-level registry, Phase 3) in sync with what was just
    ingested — per docs/phase-4-knowledge-base/metadata-schema.md, both are derived from the
    same source front-matter and must not be allowed to drift apart."""
    db = db if db is not None else get_database()
    now = datetime.now(timezone.utc)

    by_doc: dict[str, list[Chunk]] = {}
    for c in chunks:
        by_doc.setdefault(c.doc_id, []).append(c)

    for doc_chunks in by_doc.values():
        first = doc_chunks[0]
        await db.documents_meta.update_one(
            {"title": first.title, "version": first.doc_version},
            {
                "$set": {
                    "source_type": first.category,
                    "approved_pricing": first.approved_pricing,
                    "chunk_count": len(doc_chunks),
                    "is_active": True,
                    "ingested_at": now,
                }
            },
            upsert=True,
        )


def run_ingestion(
    source_dir: Path | None = None,
    collection: Collection | None = None,
    sync_mongo: bool = True,
) -> dict:
    source_dir = source_dir or Path(settings.kb_source_dir)
    chunks = load_and_chunk_source_dir(source_dir)
    result = ingest_chunks(chunks, collection=collection)
    logger.info("Ingestion result: %s", result)

    if sync_mongo:
        asyncio.run(sync_documents_meta(chunks))

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_ingestion()

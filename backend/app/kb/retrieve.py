"""
Minimal retrieval helper: embed a query, run a top-k similarity search against ChromaDB.

This is NOT the Phase 7 RAG pipeline — no re-ranking, no context assembly, no PRICING gate
enforcement. It exists to (a) give Phase 5's retrieval smoke test something to call, and
(b) be the one piece Phase 7 will actually build on top of, rather than reimplementing the
Chroma query call.
"""

from dataclasses import dataclass

from chromadb.api.models.Collection import Collection

from app.kb.chroma_client import get_kb_collection
from app.kb.embedder import embed_texts


@dataclass
class RetrievedChunk:
    chunk_id: str
    text: str
    metadata: dict
    distance: float


def retrieve(query: str, top_k: int = 3, collection: Collection | None = None) -> list[RetrievedChunk]:
    collection = collection if collection is not None else get_kb_collection()
    query_vector = embed_texts([query])[0]
    results = collection.query(query_embeddings=[query_vector], n_results=top_k)

    return [
        RetrievedChunk(chunk_id=id_, text=doc, metadata=meta, distance=dist)
        for id_, doc, meta, dist in zip(
            results["ids"][0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        )
    ]

"""
Cross-encoder re-ranking — self-hosted, same sentence-transformers family as the Phase 5
embedding model (no new dependency, no external API). Bi-encoder embedding similarity
(app/kb/retrieve.py) is fast but query and chunk are encoded independently; a cross-encoder
scores the (query, chunk) pair jointly, which is slower but more accurate — worth the extra
cost for the top-k candidates only, not the whole collection.
"""

from dataclasses import dataclass
from functools import lru_cache

from sentence_transformers import CrossEncoder

from app.kb.retrieve import RetrievedChunk

CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@dataclass
class RankedChunk:
    chunk_id: str
    text: str
    metadata: dict
    relevance_score: float  # cross-encoder score — HIGHER is more relevant (unlike
    # RetrievedChunk.distance, which is embedding distance where LOWER is more similar; kept as
    # a distinct type/field name deliberately so the two are never confused downstream).


@lru_cache
def get_reranker() -> CrossEncoder:
    return CrossEncoder(CROSS_ENCODER_MODEL)


def rerank(query: str, chunks: list[RetrievedChunk], top_n: int | None = None) -> list[RankedChunk]:
    if not chunks:
        return []

    model = get_reranker()
    scores = model.predict([(query, c.text) for c in chunks])

    ranked = [
        RankedChunk(chunk_id=c.chunk_id, text=c.text, metadata=c.metadata, relevance_score=float(score))
        for c, score in zip(chunks, scores)
    ]
    ranked.sort(key=lambda c: c.relevance_score, reverse=True)

    return ranked[:top_n] if top_n else ranked

from app.kb.retrieve import RetrievedChunk
from app.rag.reranker import rerank


def _chunk(chunk_id, text, **meta):
    return RetrievedChunk(chunk_id=chunk_id, text=text, metadata=meta, distance=0.5)


def test_rerank_orders_more_relevant_chunk_first():
    chunks = [
        _chunk("c1", "The Pro plan costs 899 rupees per vehicle per month."),
        _chunk("c2", "Geofencing lets you draw a virtual boundary around a site."),
    ]
    ranked = rerank("how does geofencing work?", chunks)
    assert ranked[0].chunk_id == "c2"
    assert ranked[0].relevance_score > ranked[1].relevance_score


def test_rerank_empty_input_returns_empty():
    assert rerank("anything", []) == []


def test_rerank_respects_top_n():
    chunks = [_chunk(f"c{i}", f"chunk number {i} about geofencing") for i in range(5)]
    ranked = rerank("geofencing", chunks, top_n=2)
    assert len(ranked) == 2


def test_rerank_preserves_metadata():
    chunks = [_chunk("c1", "Geofencing overview text", doc_id="geofencing-feature-guide", approved_pricing=False)]
    ranked = rerank("geofencing", chunks)
    assert ranked[0].metadata["doc_id"] == "geofencing-feature-guide"
    assert ranked[0].metadata["approved_pricing"] is False

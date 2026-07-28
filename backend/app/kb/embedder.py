"""
Self-hosted embedding model wrapper — no external embedding API, per the roadmap's fixed tech
stack. Kept as a thin, swappable wrapper (model name is a config value, not hardcoded at call
sites) even though only one embedding backend is in scope for this build.
"""

from functools import lru_cache

from sentence_transformers import SentenceTransformer

from app.core.config import settings


@lru_cache
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(settings.embedding_model_name)


def embed_texts(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
    return vectors.tolist()

from functools import lru_cache

import chromadb
from chromadb.api.models.Collection import Collection

from app.core.config import settings


@lru_cache
def get_chroma_client(persist_dir: str | None = None) -> chromadb.ClientAPI:
    return chromadb.PersistentClient(path=persist_dir or settings.chroma_persist_dir)


def get_kb_collection(
    client: chromadb.ClientAPI | None = None, collection_name: str | None = None
) -> Collection:
    client = client or get_chroma_client()
    return client.get_or_create_collection(
        name=collection_name or settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )

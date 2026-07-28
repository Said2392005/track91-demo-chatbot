from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://127.0.0.1:27017"
    mongo_db_name: str = "fleet_chatbot"

    kb_source_dir: str = "kb_sources"
    chroma_persist_dir: str = ".chroma_data"
    chroma_collection_name: str = "kb_chunks"
    # Self-hosted, no external embedding API (roadmap constraint). all-MiniLM-L6-v2 chosen over
    # bge-m3 for this build: KB content is short, English-only, operational text — MiniLM's
    # speed/footprint (~80MB, 384-dim, fast on CPU) matters more here than bge-m3's
    # multilingual/long-context strength, which this KB doesn't need. Swappable via env later.
    embedding_model_name: str = "all-MiniLM-L6-v2"


settings = Settings()

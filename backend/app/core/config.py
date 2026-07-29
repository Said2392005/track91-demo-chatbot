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

    # LLM provider selection (ADR 002: strategy pattern, config-driven, no SDK in business
    # logic). No credentials configured in this build — see docs/phase-6-semantic-analysis/.
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    # Groq (app/llm/providers/groq.py): free-tier OpenAI-compatible alternative actually used
    # for Phase 12's real-model verification, since a paid DeepSeek key wasn't available.
    groq_api_key: str = ""

    # Phase 6: which intent-classification strategy is active by default. "llm" requires a
    # configured, working llm_provider; "rule_based" needs nothing but this codebase.
    intent_classifier_strategy: str = "rule_based"

    # Entity extraction assumption carried from docs/phase-1-planning/non-goals.md — confirm
    # before this becomes load-bearing for a non-India deployment.
    default_timezone: str = "Asia/Kolkata"

    # Phase 7: opt-in, not default. Measured worse than raw retrieval on this KB's size
    # (precision@3: 0.875 reranked vs 0.9375 retrieval-only — see docs/phase-7-rag-pipeline/
    # rag-pipeline.md) while adding a second model's load+inference cost per query. Re-enable
    # once the KB is large/heterogeneous enough to plausibly benefit, and re-measure first.
    rag_use_reranker: bool = False

    # Phase 8: conversation memory must expire, not persist indefinitely.
    # - session_ttl_seconds: whole session (chat_sessions doc + LangGraph checkpoint) idle
    #   expiry. 24h default — generous enough that a user returning later same-day resumes
    #   their session, short enough not to accumulate abandoned sessions forever.
    # - active_entity_ttl_seconds: separate, shorter — "its speed" resolving to a vehicle
    #   discussed 3 hours ago in an otherwise-still-open session would be confusing even if the
    #   session itself hasn't expired. 30 min default. Flagged assumption: both are guesses at
    #   reasonable pilot defaults, not measured against real usage patterns.
    session_ttl_seconds: int = 24 * 60 * 60
    active_entity_ttl_seconds: int = 30 * 60

    # Phase 11: JWT auth. No production default for jwt_secret_key — deliberately not given a
    # baked-in fallback, so a deployment that forgets to set it fails loudly at startup rather
    # than silently signing tokens with a well-known string. Fine to be empty for local dev
    # (tests set their own).
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 12  # 12h

    log_level: str = "INFO"


settings = Settings()

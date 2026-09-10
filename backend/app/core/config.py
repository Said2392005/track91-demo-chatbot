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
    # logic). AWS Bedrock (app/llm/providers/bedrock.py) via the Converse API: the active
    # real-model provider for this build. Amazon Nova Lite, addressed by its APAC inference
    # profile ARN (on-demand invocation of this model/region requires an inference profile
    # rather than the bare model ID) — per the reference implementation this was matched
    # against, not gpt-oss-120b/us-east-1 (invoke_model), which this build used previously.
    # Credentials still never live in .env or this file — only the non-secret model/region/
    # profile are configured here.
    llm_provider: str = "bedrock"
    bedrock_model_id: str = "arn:aws:bedrock:ap-south-1::inference-profile/apac.amazon.nova-lite-v1:0"
    bedrock_region: str = "ap-south-1"
    # Named AWS profile the Bedrock adapter builds its boto3 session from — explicit in code,
    # not picked up from whatever AWS_PROFILE happens to be exported in the current shell. Was
    # "office" (arn:...:user/ai-intern, account 516035591988); that profile's credentials are no
    # longer present in this machine's ~/.aws/credentials (reproduced: boto3.Session(profile_
    # name="office") -> NoCredentialsError regardless of shell state, confirmed via sts:GetCall
    # erIdentity run directly against it) — not a code bug, the named profile just doesn't have
    # keys anymore. "personal" (arn:...:user/student-result-admin, account 390281678718) is the
    # profile that currently resolves; confirmed directly the same way before changing this.
    # Set to "" for production/containers, where boto3's default credential chain (an IAM role)
    # should be used instead of a named profile that won't exist there — see
    # app/llm/providers/bedrock.py's __init__.
    aws_profile: str = "personal"

    # Phase 6: which intent-classification strategy is active by default. "llm" requires a
    # configured, working llm_provider; "rule_based" needs nothing but this codebase.
    intent_classifier_strategy: str = "rule_based"

    # Passed as max_completion_tokens/max_tokens on every real LLM call (intent classification
    # when using the "llm" strategy, response synthesis, RAG generation, general knowledge) to
    # cap completion-token usage. 250 was right for Groq/Llama-3.3 (200 truncated the
    # TROUBLESHOOTING_DEVICE answer ~1/6 real repeated calls; 250 cleared 12/12) but gpt-oss on
    # Bedrock spends completion tokens on a <reasoning>...</reasoning> block *before* the visible
    # answer (app/llm/providers/bedrock.py strips it), shrinking the effective answer budget for
    # the same cap — 250 and even 350 still truncated the same TROUBLESHOOTING_DEVICE case on
    # Bedrock (350: 1/6 real repeated calls). Re-measured on Bedrock/gpt-oss-120b: 450 cleared
    # 6/6, worst observed completion_tokens 428; 500 cleared a further 6/6 with more headroom
    # (worst observed 388) and is what's set here. See docs/phase-12-testing/testing.md's
    # token-usage section and tests/test_max_tokens_real_bedrock.py for the full measurement —
    # tune here, not per call site, if usage needs differ later.
    llm_max_tokens: int = 500

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

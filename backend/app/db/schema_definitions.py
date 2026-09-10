"""
JSON Schema validators for every MongoDB collection.

Reshaped from the relational DBML supplied 2026-08-12 (organizations/users/products/
categories/features/services/api_keys/auth_sessions/documents/document_chunks/
knowledge_items/prompt_configurations/chat_sessions/messages) into Mongo-idiomatic
collections rather than a literal 1:1 copy:

- Integer PKs/FKs -> ObjectId `_id` and ObjectId reference fields (matches this codebase's
  existing convention of flat, top-level, ObjectId-referenced collections rather than deep
  embedding).
- `messages` renamed to `chat_messages` for consistency with this codebase's naming.
- Organization contact fields (primary/support/billing email, primary/support phone) and
  postal address fields (address_line1/2, city, state, country, postal_code) collapsed into
  nested `contacts` / `address` subdocuments on `organizations` — they're always read/written
  together and have no independent query pattern of their own.
- `json` columns (items, keywords, metadata) map to native BSON array/object types instead of
  an opaque blob type.

Known gaps carried over from the source DBML, not resolved here:
- `organizations.plan_id` references a `plans` table that does not exist in the supplied
  DBML. Kept as an untyped ObjectId placeholder; tighten once a plans collection exists.
- The DBML has no enums for `status`/`role`/`content_type`/`category`/`environment` fields
  (all plain `varchar` in the source). Unlike the previous fleet schema (which defined
  ALERT_TYPES, VEHICLE_STATUSES, etc. from actual product requirements), no allowed-value
  list is fabricated here — these are left as unconstrained strings until product defines them.
- `messages.prompt_tokens/output_tokens/total_tokens` models one LLM call per message. The
  previous schema's `llm_usage` collection tracked up to 4 distinct LLM calls per turn
  (intent_classification, response_synthesis, rag_generation, general_knowledge) via a
  `call_type` field with no analog here — multi-call-per-turn usage tracking has no home in
  this schema as given.
"""

_OBJECT_ID = {"bsonType": "objectId"}
_STRING = {"bsonType": "string"}
_DATE = {"bsonType": "date"}
_BOOL = {"bsonType": "bool"}
_INT = {"bsonType": "int"}
_DOUBLE = {"bsonType": ["double", "int"]}
_ARRAY = {"bsonType": "array"}
_OBJECT = {"bsonType": "object"}


def _schema(title: str, required: list[str], properties: dict) -> dict:
    return {
        "$jsonSchema": {
            "bsonType": "object",
            "title": title,
            "required": required,
            "properties": {"_id": _OBJECT_ID, **properties},
        }
    }


COLLECTION_VALIDATORS: dict[str, dict] = {
    "organizations": _schema(
        "Organization",
        required=["plan_id", "name", "status", "created_at"],
        properties={
            "plan_id": _OBJECT_ID,  # forward reference — no `plans` collection defined yet
            "name": _STRING,
            "legal_name": _STRING,
            "organization_code": _STRING,  # unique — see indexes.py
            "short_description": _STRING,
            "long_description": _STRING,
            "industry": _STRING,
            "organization_type": _STRING,
            "website_url": _STRING,
            "logo_url": _STRING,
            "contacts": {
                "bsonType": "object",
                "properties": {
                    "primary_email": _STRING,
                    "support_email": _STRING,
                    "billing_email": _STRING,
                    "primary_phone": _STRING,
                    "support_phone": _STRING,
                },
            },
            "address": {
                "bsonType": "object",
                "properties": {
                    "line1": _STRING,
                    "line2": _STRING,
                    "city": _STRING,
                    "state": _STRING,
                    "country": _STRING,
                    "postal_code": _STRING,
                },
            },
            "timezone": _STRING,
            "currency": _STRING,
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "users": _schema(
        "User",
        required=["org_id", "email", "status", "created_at"],
        properties={
            "org_id": _OBJECT_ID,
            "name": _STRING,
            "email": _STRING,  # unique — see indexes.py
            "password_hash": _STRING,
            "role": _STRING,
            "status": _STRING,
            "last_login_at": _DATE,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "products": _schema(
        "Product",
        required=["org_id", "title", "status", "created_at"],
        properties={
            "org_id": _OBJECT_ID,
            "content_type": _STRING,
            "category": _STRING,
            "title": _STRING,
            "short_description": _STRING,
            "long_description": _STRING,
            "items": _ARRAY,
            "keywords": {"bsonType": "array", "items": _STRING},
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "categories": _schema(
        "Category",
        required=["product_id", "name", "created_at"],
        properties={
            "product_id": _OBJECT_ID,
            "name": _STRING,
            "slug": _STRING,
            "description": _STRING,
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "features": _schema(
        "Feature",
        required=["product_id", "title", "created_at"],
        properties={
            "product_id": _OBJECT_ID,
            "category_id": _OBJECT_ID,
            "title": _STRING,
            "short_description": _STRING,
            "long_description": _STRING,
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "services": _schema(
        "Service",
        required=["product_id", "title", "created_at"],
        properties={
            "product_id": _OBJECT_ID,
            "category_id": _OBJECT_ID,
            "title": _STRING,
            "short_description": _STRING,
            "long_description": _STRING,
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "api_keys": _schema(
        "ApiKey",
        required=["org_id", "key_hash", "created_at"],
        properties={
            "org_id": _OBJECT_ID,
            "product_id": _OBJECT_ID,
            "key_name": _STRING,
            "key_hash": _STRING,
            "provider": _STRING,
            "environment": _STRING,
            "status": _STRING,
            "expires_at": _DATE,
            "last_used_at": _DATE,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "auth_sessions": _schema(
        "AuthSession",
        required=["user_id", "created_at"],
        properties={
            "user_id": _OBJECT_ID,
            "access_token_hash": _STRING,
            "refresh_token_hash": _STRING,
            "ip_address": _STRING,
            "user_agent": _STRING,
            "status": _STRING,
            "expires_at": _DATE,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "documents": _schema(
        "Document",
        required=["product_id", "created_at"],
        properties={
            "product_id": _OBJECT_ID,
            "title": _STRING,
            "document_type": _STRING,
            "source_type": _STRING,
            "source_url": _STRING,
            "file_name": _STRING,
            "file_type": _STRING,
            "file_path": _STRING,
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "document_chunks": _schema(
        "DocumentChunk",
        required=["document_id", "product_id", "content", "created_at"],
        properties={
            "document_id": _OBJECT_ID,
            "product_id": _OBJECT_ID,
            "chunk_index": _INT,
            "content": _STRING,
            "token_count": _INT,
            "vector_id": _STRING,
            "metadata": _OBJECT,
            "created_at": _DATE,
        },
    ),
    "knowledge_items": _schema(
        "KnowledgeItem",
        required=["product_id", "title", "created_at"],
        properties={
            "product_id": _OBJECT_ID,
            "content_type": _STRING,
            "category": _STRING,
            "title": _STRING,
            "short_description": _STRING,
            "long_description": _STRING,
            "items": _ARRAY,
            "keywords": {"bsonType": "array", "items": _STRING},
            "status": _STRING,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "prompt_configurations": _schema(
        "PromptConfiguration",
        required=["product_id", "created_at"],
        properties={
            "product_id": _OBJECT_ID,
            "name": _STRING,
            "system_prompt": _STRING,
            "model_provider": _STRING,
            "model_name": _STRING,
            "temperature": _DOUBLE,
            "max_tokens": _INT,
            "is_active": _BOOL,
            "created_at": _DATE,
            "updated_at": _DATE,
        },
    ),
    "chat_sessions": _schema(
        "ChatSession",
        required=["product_id", "status", "started_at", "last_active_at"],
        properties={
            "product_id": _OBJECT_ID,
            "prompt_id": _OBJECT_ID,
            "user_id": _OBJECT_ID,
            "session_key": _STRING,  # unique — see indexes.py
            "ip_hash": _STRING,
            "status": _STRING,
            "started_at": _DATE,
            "ended_at": _DATE,
            "last_active_at": _DATE,
        },
    ),
    "chat_messages": _schema(
        "ChatMessage",
        required=["session_id", "role", "content", "created_at"],
        properties={
            "session_id": _OBJECT_ID,
            "role": _STRING,
            "content": _STRING,
            "model_provider": _STRING,
            "model_name": _STRING,
            "prompt_tokens": _INT,
            "output_tokens": _INT,
            "total_tokens": _INT,
            "latency_ms": _INT,
            "status": _STRING,
            "created_at": _DATE,
        },
    ),
}

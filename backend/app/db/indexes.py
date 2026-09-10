"""
Index definitions per collection.

Reshaped alongside schema_definitions.py for the 2026-08-12 DBML redesign. Compound indexes
still lead with the collection's tenant/parent-scoping field (org_id, product_id, etc.) where
the DBML implies one, following this codebase's existing access-path convention — but no
TTL or uniqueness constraint is added beyond what the DBML actually states. The previous
schema's `session_ttl_idx` (sliding idle-timeout on chat_sessions) was a Phase 8 product
requirement, not something implied by a relational schema; whether chat_sessions in this new
domain should also auto-expire is an open product question, not assumed here.
"""

from pymongo import ASCENDING

# Each entry: (keys: list[(field, direction)], options: dict)
INDEX_DEFINITIONS: dict[str, list[tuple[list[tuple[str, int]], dict]]] = {
    "organizations": [
        (
            [("organization_code", ASCENDING)],
            {
                "name": "organization_code_unique",
                "unique": True,
                # organization_code is [unique] but not [not null] in the source DBML —
                # partialFilterExpression (not sparse) so multiple docs missing it don't
                # collide, same reasoning as the old company_device_unique index had.
                "partialFilterExpression": {"organization_code": {"$exists": True}},
            },
        ),
    ],
    "users": [
        ([("email", ASCENDING)], {"name": "email_unique", "unique": True}),
        ([("org_id", ASCENDING)], {"name": "org_idx"}),
    ],
    "products": [
        ([("org_id", ASCENDING)], {"name": "org_idx"}),
        ([("org_id", ASCENDING), ("status", ASCENDING)], {"name": "org_status_idx"}),
    ],
    "categories": [
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
    ],
    "features": [
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
        ([("category_id", ASCENDING)], {"name": "category_idx"}),
    ],
    "services": [
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
        ([("category_id", ASCENDING)], {"name": "category_idx"}),
    ],
    "api_keys": [
        ([("org_id", ASCENDING)], {"name": "org_idx"}),
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
        ([("key_hash", ASCENDING)], {"name": "key_hash_idx"}),
    ],
    "auth_sessions": [
        ([("user_id", ASCENDING)], {"name": "user_idx"}),
        ([("access_token_hash", ASCENDING)], {"name": "access_token_idx"}),
        ([("refresh_token_hash", ASCENDING)], {"name": "refresh_token_idx"}),
    ],
    "documents": [
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
    ],
    "document_chunks": [
        ([("document_id", ASCENDING), ("chunk_index", ASCENDING)], {"name": "document_chunk_idx"}),
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
        ([("vector_id", ASCENDING)], {"name": "vector_id_idx"}),
    ],
    "knowledge_items": [
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
    ],
    "prompt_configurations": [
        ([("product_id", ASCENDING)], {"name": "product_idx"}),
        ([("product_id", ASCENDING), ("is_active", ASCENDING)], {"name": "product_active_idx"}),
    ],
    "chat_sessions": [
        ([("session_key", ASCENDING)], {"name": "session_key_unique", "unique": True}),
        ([("product_id", ASCENDING), ("last_active_at", ASCENDING)], {"name": "product_activity_idx"}),
        ([("user_id", ASCENDING)], {"name": "user_idx"}),
    ],
    "chat_messages": [
        ([("session_id", ASCENDING), ("created_at", ASCENDING)], {"name": "session_time_idx"}),
    ],
}

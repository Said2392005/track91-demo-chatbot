"""
Index existence tests — Phase 3 testing requirement (roadmap.md).

Verifies every index declared in app/db/indexes.py actually exists on the server after
init_db() runs, and that tenant-scoped collections lead their compound indexes with
company_id (ADR 004 — docs/phase-2-architecture/adr/004-tenant-scoping-enforcement.md).
"""

import pytest

from app.db.indexes import INDEX_DEFINITIONS

TENANT_SCOPED_COLLECTIONS = {
    "users",
    "vehicles",
    "drivers",
    "trips",
    "alerts",
    "maintenance_records",
    "geofences",
    "chat_sessions",
    "chat_messages",
}


@pytest.mark.parametrize("collection", INDEX_DEFINITIONS.keys())
async def test_declared_indexes_exist(db, collection):
    actual = {idx["name"]: idx["key"] async for idx in db[collection].list_indexes()}

    for keys, options in INDEX_DEFINITIONS[collection]:
        name = options["name"]
        assert name in actual, f"expected index {name!r} missing on {collection!r}"
        expected_keys = dict(keys)
        assert dict(actual[name]) == expected_keys, (
            f"index {name!r} on {collection!r} has keys {dict(actual[name])}, expected {expected_keys}"
        )


@pytest.mark.parametrize("collection", sorted(TENANT_SCOPED_COLLECTIONS))
async def test_tenant_scoped_collections_have_company_id_leading_index(db, collection):
    indexes = {idx["name"]: list(idx["key"].keys()) async for idx in db[collection].list_indexes()}
    compound_or_scoped = [
        keys for name, keys in indexes.items() if name != "_id_" and "company_id" in keys
    ]
    assert compound_or_scoped, f"{collection!r} has no company_id-scoped index at all"
    assert all(keys[0] == "company_id" for keys in compound_or_scoped), (
        f"{collection!r} has a company_id index that doesn't lead with company_id: {compound_or_scoped}"
    )

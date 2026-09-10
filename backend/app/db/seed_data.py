"""
Seed data: real Track91 content plus the pre-existing synthetic "Cosmica Test Org" fixture.

`seed_track91()` is transcribed verbatim from the live Track91 marketing site (hero copy,
feature blocks, reporting section, "Built for every fleet" vehicle-type list, and the full
Privacy Policy) as supplied 2026-08-13 — real product content, not placeholder filler.

`seed_cosmica_test_fixture()` is kept as-is from the earlier 2026-08-12 DBML-redesign fixture:
it's a minimal synthetic org/user/session set that exercises every collection/index and backs
loadtest/locustfile.py's login (admin@cosmica-test.example / demo1234) — removing it would
silently break that documented load-test flow, so both fixtures now run side by side.

Mapping notes (Track91):
- organizations.plan_id is required by the DBML but no `plans` collection exists yet (see
  schema_definitions.py's "Known gaps") — a placeholder ObjectId satisfies the validator only.
- No domain/website URL appears anywhere in the supplied site copy (only a "Get it on Google
  Play" CTA and the track91.app@gmail.com contact address) — website_url is deliberately left
  unset rather than invented.
- organizations has no dedicated "compliance" field, so the privacy-policy facts that are
  compliance-relevant at the org level (what's collected, encryption in transit, no sale of
  data, access restricted to the account holder) are folded into organizations.long_description
  using the policy's own wording. The full policy text itself — the actually useful, searchable
  KB content — lives in documents + document_chunks (one chunk per policy section), matching
  this schema's existing document_chunks.content usage for RAG (see document_chunk_repository.py).
- features.short_description holds each feature block's real badge label (REAL-TIME, MAP
  TRACKING, ...); features.long_description holds the block's real description sentence.
- categories are the vehicle types from the "Built for every fleet" list. No per-vehicle-type
  description exists in the source copy, so none is fabricated — description is left unset.
- services are the three real bullets under "Reporting"; short_description is the section's
  real intro sentence, shared across all three since the source doesn't give per-bullet copy.

Idempotent: keyed upserts on natural keys (organization_code, product title, feature/service/
category title within the product, document title) so re-running this script does not create
duplicates.

Usage: python -m app.db.seed_data
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import hash_password
from app.db.client import get_database
from app.db.init_db import init_db

# A login-capable demo account so the synthetic Cosmica Test fixture is directly usable for
# end-to-end manual testing (POST /auth/login) and loadtest/locustfile.py. Synthetic dev-only
# data — never use this password beyond a local/dev instance.
DEMO_PASSWORD = "demo1234"  # noqa: S105 (not a real secret — local dev seed data only)

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def seed(db: AsyncIOMotorDatabase | None = None) -> None:
    db = db if db is not None else get_database()
    await init_db(db)

    await seed_track91(db)
    await seed_cosmica_test_fixture(db)


async def seed_track91(db: AsyncIOMotorDatabase) -> None:
    now = _now()

    # --- organizations --------------------------------------------------------------------
    org_id = (
        await db.organizations.find_one_and_update(
            {"organization_code": "TRACK91"},
            {
                "$setOnInsert": {
                    # plan_id is required by the DBML but no `plans` collection exists to
                    # reference — see schema_definitions.py's "Known gaps". A random ObjectId
                    # placeholder, not a real reference, is used here only to satisfy the
                    # `bsonType: objectId` validator.
                    "plan_id": ObjectId(),
                    "name": "Track91",
                    "legal_name": "Track-91",
                    "organization_code": "TRACK91",
                    "organization_type": "vendor",
                    "industry": "GPS Fleet Tracking / Transport Technology",
                    "short_description": (
                        "AIS-140 compliant GPS tracking for cars, trucks, buses, logistics "
                        "fleets and EVs"
                    ),
                    "long_description": (
                        "Track91 connects with AIS-140 compliant GPS devices to track cars, "
                        "trucks, buses, logistics fleets and EVs in real time — built for "
                        "India's government-mandated standard for commercial and public "
                        "transport vehicles. To provide AIS-140 GPS tracking services, Track91 "
                        "collects the IMEI number of any registered AIS-140 compliant GPS "
                        "device, real-time and historical location data reported by registered "
                        "devices, vehicle status data such as speed and ignition state, and "
                        "basic account information (name, email address, phone number). "
                        "Location and account data are encrypted in transit, and access to "
                        "your data is restricted to your account. Track91 does not sell "
                        "location or account data — information is only shared with trusted "
                        "service providers, such as map and cloud infrastructure providers, "
                        "strictly to operate the app."
                    ),
                    "contacts": {"primary_email": "track91.app@gmail.com"},
                    "address": {"country": "India"},
                    "status": "active",
                    "created_at": now,
                }
            },
            upsert=True,
            return_document=True,
        )
    )["_id"]

    # --- products --------------------------------------------------------------------------
    product_doc = await db.products.find_one_and_update(
        {"org_id": org_id, "title": "Track91 AIS-140 GPS Tracking App"},
        {
            "$setOnInsert": {
                "org_id": org_id,
                "content_type": "app",
                "category": "GPS Fleet Tracking",
                "title": "Track91 AIS-140 GPS Tracking App",
                "short_description": (
                    "AIS-140 compliant GPS tracking for cars, trucks, buses, logistics fleets "
                    "and EVs"
                ),
                "long_description": (
                    "Register an IMEI. Track it live. Track91 connects with AIS-140 compliant "
                    "GPS devices to track cars, trucks, buses, logistics fleets and EVs in real "
                    "time — built for India's government-mandated standard for commercial and "
                    "public transport vehicles. AIS-140 is a government-mandated GPS tracking "
                    "standard in India, designed for commercial and public transport vehicles. "
                    "It sets out how vehicle tracking devices must report location and status "
                    "data. Track91 supports AIS-140 compliant tracking systems, so transport "
                    "operators get reliable location monitoring, vehicle visibility and fleet "
                    "management — while staying aligned with the standard. Track91 receives "
                    "location data directly from installed AIS-140 GPS devices for reliable, "
                    "industry-ready tracking."
                ),
                "items": [],
                "keywords": [
                    "AIS-140",
                    "GPS tracking",
                    "fleet management",
                    "EV tracking",
                    "IMEI",
                ],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=True,
    )
    product_id = product_doc["_id"]

    # --- categories: vehicle types from "Built for every fleet" -----------------------------
    vehicle_categories = [
        ("Cars", "cars"),
        ("Trucks", "trucks"),
        ("Buses", "buses"),
        ("Commercial vehicles", "commercial-vehicles"),
        ("Logistics fleets", "logistics-fleets"),
        ("Delivery vehicles", "delivery-vehicles"),
        ("Public transport vehicles", "public-transport-vehicles"),
        ("Electric vehicles (EVs)", "electric-vehicles-evs"),
    ]
    for name, slug in vehicle_categories:
        await db.categories.update_one(
            {"product_id": product_id, "name": name},
            {
                "$setOnInsert": {
                    "product_id": product_id,
                    "name": name,
                    "slug": slug,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    # --- features: the six "Smart tracking features" blocks ---------------------------------
    features = [
        {
            "title": "Live vehicle locations",
            "short_description": "REAL-TIME",
            "long_description": (
                "View live, accurate location data from AIS-140 compliant GPS devices "
                "installed in your vehicles."
            ),
        },
        {
            "title": "Interactive map monitoring",
            "short_description": "MAP TRACKING",
            "long_description": "Monitor vehicle movement in real time on an interactive map view.",
        },
        {
            "title": "Track multiple vehicles",
            "short_description": "MULTI-VEHICLE",
            "long_description": (
                "Track several vehicles simultaneously from a single account and dashboard."
            ),
        },
        {
            "title": "Remote fleet monitoring",
            "short_description": "FLEET",
            "long_description": (
                "Monitor fleet activity from anywhere — transport, logistics, delivery, or "
                "public transport."
            ),
        },
        {
            "title": "EV vehicle monitoring",
            "short_description": "EV READY",
            "long_description": (
                "Track electric vehicles alongside cars, trucks and buses in the same fleet "
                "view."
            ),
        },
        {
            "title": "Secure monitoring platform",
            "short_description": "SECURE",
            "long_description": (
                "Location data is encrypted and access to your vehicles is tied to your "
                "account only."
            ),
        },
    ]
    for f in features:
        await db.features.update_one(
            {"product_id": product_id, "title": f["title"]},
            {
                "$setOnInsert": {
                    "product_id": product_id,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                    **f,
                }
            },
            upsert=True,
        )

    # --- services: the three "Reporting" bullets --------------------------------------------
    reporting_intro = (
        "Generate and download detailed PDF reports to keep records, support audits, and "
        "analyse fleet performance."
    )
    services = [
        {"title": "Vehicle trip reports"},
        {"title": "Distance traveled reports"},
        {"title": "Vehicle tracking reports in PDF format"},
    ]
    for s in services:
        await db.services.update_one(
            {"product_id": product_id, "title": s["title"]},
            {
                "$setOnInsert": {
                    "product_id": product_id,
                    "short_description": reporting_intro,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                    **s,
                }
            },
            upsert=True,
        )

    # --- documents + document_chunks: the full Privacy Policy, section by section -----------
    document_doc = await db.documents.find_one_and_update(
        {"product_id": product_id, "title": "Track91 Privacy Policy"},
        {
            "$setOnInsert": {
                "product_id": product_id,
                "title": "Track91 Privacy Policy",
                "document_type": "privacy_policy",
                "source_type": "website_legal_page",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=True,
    )
    document_id = document_doc["_id"]

    policy_sections = [
        (
            "Information we collect",
            (
                "This privacy policy applies to the Track91 mobile application. To provide "
                "AIS-140 GPS tracking services, Track91 collects: the IMEI number of any "
                "AIS-140 compliant GPS device you register; real-time and historical location "
                "data reported by registered devices; vehicle status data such as speed and "
                "ignition state; and basic account information, such as your name, email "
                "address, and phone number."
            ),
        ),
        (
            "How we use this information",
            (
                "We use this data to display live vehicle locations, generate route history "
                "and PDF reports, and manage your registered devices within the app."
            ),
        ),
        (
            "Data sharing",
            (
                "We do not sell your location or account data. Information is only shared "
                "with trusted service providers — such as map and cloud infrastructure "
                "providers — strictly to operate the app."
            ),
        ),
        (
            "Data security",
            (
                "Location and account data are encrypted in transit, and access to your data "
                "is restricted to your account."
            ),
        ),
        (
            "Data retention",
            (
                "We retain tracking data for as long as your account remains active, or as "
                "needed to provide route history and reports. You can request deletion of "
                "your account and associated data at any time."
            ),
        ),
        (
            "Your consent",
            (
                "By registering a device and using Track91, you consent to the collection "
                "and use of information as described in this policy."
            ),
        ),
    ]
    for chunk_index, (section, content) in enumerate(policy_sections):
        await db.document_chunks.update_one(
            {"document_id": document_id, "chunk_index": chunk_index},
            {
                "$setOnInsert": {
                    "document_id": document_id,
                    "product_id": product_id,
                    "chunk_index": chunk_index,
                    "content": content,
                    "metadata": {"section": section},
                    "created_at": now,
                }
            },
            upsert=True,
        )

    logger.info("Track91 seed complete for org_id=%s, product_id=%s", org_id, product_id)


async def seed_cosmica_test_fixture(db: AsyncIOMotorDatabase) -> None:
    """Minimal synthetic fixture from the 2026-08-12 DBML redesign — exercises every
    collection/index and backs loadtest/locustfile.py's demo login. Not real product data."""
    now = _now()

    org_id = (
        await db.organizations.find_one_and_update(
            {"organization_code": "COSMICA-TEST"},
            {
                "$setOnInsert": {
                    # plan_id is required by the DBML but no `plans` collection exists to
                    # reference — see schema_definitions.py's "Known gaps". A random ObjectId
                    # placeholder, not a real reference, is used here only to satisfy the
                    # `bsonType: objectId` validator.
                    "plan_id": ObjectId(),
                    "name": "Cosmica Test Org",
                    "organization_code": "COSMICA-TEST",
                    "industry": "Software",
                    "organization_type": "customer",
                    "contacts": {"primary_email": "ops@cosmica-test.example"},
                    "address": {"city": "Pune", "country": "India"},
                    "timezone": "Asia/Kolkata",
                    "currency": "INR",
                    "status": "active",
                    "created_at": now,
                }
            },
            upsert=True,
            return_document=True,
        )
    )["_id"]

    users = [
        {"name": "Admin User", "email": "admin@cosmica-test.example", "role": "admin"},
        {"name": "Product Manager", "email": "pm@cosmica-test.example", "role": "manager"},
    ]
    for u in users:
        await db.users.update_one(
            {"org_id": org_id, "email": u["email"]},
            {
                "$setOnInsert": {
                    "org_id": org_id,
                    "name": u["name"],
                    "email": u["email"],
                    "role": u["role"],
                    "status": "active",
                    "password_hash": hash_password(DEMO_PASSWORD),
                    "created_at": now,
                }
            },
            upsert=True,
        )
    admin_user = await db.users.find_one({"org_id": org_id, "email": "admin@cosmica-test.example"})

    product_doc = await db.products.find_one_and_update(
        {"org_id": org_id, "title": "Cosmica Test Product"},
        {
            "$setOnInsert": {
                "org_id": org_id,
                "content_type": "app",
                "category": "productivity",
                "title": "Cosmica Test Product",
                "short_description": "A synthetic product used to exercise the schema.",
                "items": [],
                "keywords": ["test", "synthetic"],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=True,
    )
    product_id = product_doc["_id"]

    category_doc = await db.categories.find_one_and_update(
        {"product_id": product_id, "name": "Core"},
        {
            "$setOnInsert": {
                "product_id": product_id,
                "name": "Core",
                "slug": "core",
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=True,
    )
    category_id = category_doc["_id"]

    features = [
        {"title": "Dashboard", "short_description": "At-a-glance overview."},
        {"title": "Notifications", "short_description": "Configurable alert delivery."},
    ]
    for f in features:
        await db.features.update_one(
            {"product_id": product_id, "title": f["title"]},
            {
                "$setOnInsert": {
                    "product_id": product_id,
                    "category_id": category_id,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                    **f,
                }
            },
            upsert=True,
        )

    services = [
        {"title": "Onboarding", "short_description": "Guided setup for new organizations."},
    ]
    for s in services:
        await db.services.update_one(
            {"product_id": product_id, "title": s["title"]},
            {
                "$setOnInsert": {
                    "product_id": product_id,
                    "category_id": category_id,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                    **s,
                }
            },
            upsert=True,
        )

    await db.prompt_configurations.update_one(
        {"product_id": product_id, "name": "default"},
        {
            "$setOnInsert": {
                "product_id": product_id,
                "name": "default",
                "system_prompt": "You are a helpful assistant for Cosmica Test Product.",
                "model_provider": "bedrock",
                "model_name": "anthropic.claude-3-haiku",
                "temperature": 0.2,
                "max_tokens": 1024,
                "is_active": True,
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    documents = [
        {"title": "Product FAQ", "document_type": "faq", "source_type": "app_faq"},
        {"title": "Getting Started Guide", "document_type": "guide", "source_type": "feature_guide"},
    ]
    for doc in documents:
        await db.documents.update_one(
            {"product_id": product_id, "title": doc["title"]},
            {
                "$setOnInsert": {
                    "product_id": product_id,
                    "status": "active",
                    "created_at": now,
                    "updated_at": now,
                    **doc,
                }
            },
            upsert=True,
        )

    await db.knowledge_items.update_one(
        {"product_id": product_id, "title": "Supported Browsers"},
        {
            "$setOnInsert": {
                "product_id": product_id,
                "content_type": "faq_item",
                "title": "Supported Browsers",
                "short_description": "Chrome, Firefox, Safari, Edge (latest two major versions).",
                "keywords": ["browser", "compatibility"],
                "status": "active",
                "created_at": now,
                "updated_at": now,
            }
        },
        upsert=True,
    )

    session_doc = await db.chat_sessions.find_one_and_update(
        {"product_id": product_id, "user_id": admin_user["_id"], "status": "active"},
        {
            "$setOnInsert": {
                "product_id": product_id,
                "user_id": admin_user["_id"],
                "session_key": f"seed-session-{admin_user['_id']}",
                "status": "active",
                "started_at": now,
                "last_active_at": now,
            }
        },
        upsert=True,
        return_document=True,
    )
    sample_messages = [
        {"role": "user", "content": "What browsers are supported?"},
        {"role": "assistant", "content": "Chrome, Firefox, Safari, and Edge — latest two major versions."},
    ]
    for i, m in enumerate(sample_messages):
        await db.chat_messages.update_one(
            {"session_id": session_doc["_id"], "content": m["content"]},
            {
                "$setOnInsert": {
                    "session_id": session_doc["_id"],
                    "created_at": now + timedelta(seconds=i),
                    **m,
                }
            },
            upsert=True,
        )

    logger.info("Cosmica test fixture seed complete for org_id=%s, product_id=%s", org_id, product_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())

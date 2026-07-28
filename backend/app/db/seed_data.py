"""
Synthetic seed data — NONE of this represents a real company, vehicle, or person.
Per docs/phase-1-planning/non-goals.md ("all data is mocked/synthetic for this build"), this
exists purely to exercise the schema, indexes, and later phases (RAG golden set, eval harness).

Idempotent: keyed upserts on natural keys (company name, plate_number, driver name, etc.) so
re-running this script does not create duplicates.

Usage: python -m app.db.seed_data
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.client import get_database
from app.db.init_db import init_db

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Fixed reference point for derived record timestamps (trip/alert/maintenance dates) used in
# upsert filter keys. Deriving these from wall-clock `now()` instead would make the filter key
# a moving target — a re-run at a different time would insert duplicates rather than match the
# existing doc. `created_at`/`ingested_at`/etc. below are fine to timestamp with real `now()`
# since they're only ever written via $setOnInsert (once, at first insert).
SEED_ANCHOR = datetime(2026, 7, 27, 6, 0, tzinfo=timezone.utc)


async def seed(db: AsyncIOMotorDatabase | None = None) -> None:
    db = db if db is not None else get_database()
    await init_db(db)

    now = _now()

    company_id = (
        await db.companies.find_one_and_update(
            {"name": "Cosmica Test Fleets Pvt Ltd"},
            {
                "$setOnInsert": {
                    "name": "Cosmica Test Fleets Pvt Ltd",
                    "status": "active",
                    "timezone": "Asia/Kolkata",
                    "created_at": now,
                }
            },
            upsert=True,
            return_document=True,
        )
    )["_id"]

    users = [
        {"name": "Admin User", "email": "admin@cosmica-test.example", "role": "admin"},
        {"name": "Fleet Manager", "email": "fleetmgr@cosmica-test.example", "role": "fleet_manager"},
    ]
    for u in users:
        await db.users.update_one(
            {"company_id": company_id, "email": u["email"]},
            {
                "$setOnInsert": {
                    "company_id": company_id,
                    "name": u["name"],
                    "email": u["email"],
                    "role": u["role"],
                    "status": "active",
                    "created_at": now,
                }
            },
            upsert=True,
        )

    drivers = [
        {"name": "Ramesh Kumar", "phone": "+91-9800000001", "license_number": "MH-DL-0001"},
        {"name": "Suresh Patil", "phone": "+91-9800000002", "license_number": "MH-DL-0002"},
        {"name": "Anita Sharma", "phone": "+91-9800000003", "license_number": "KA-DL-0003"},
    ]
    driver_ids: dict[str, object] = {}
    for d in drivers:
        doc = await db.drivers.find_one_and_update(
            {"company_id": company_id, "name": d["name"]},
            {
                "$setOnInsert": {
                    "company_id": company_id,
                    "name": d["name"],
                    "phone": d["phone"],
                    "license_number": d["license_number"],
                    "status": "active",
                    "created_at": now,
                }
            },
            upsert=True,
            return_document=True,
        )
        driver_ids[d["name"]] = doc["_id"]

    vehicles = [
        {
            "plate_number": "MH12AB1234",
            "nickname": "Pune Van",
            "make": "Tata",
            "model": "Ace",
            "year": 2022,
            "vehicle_type": "van",
            "fleet_group": "Mumbai Fleet",
            "device_id": "DEV-0001",
            "assigned_driver": "Ramesh Kumar",
        },
        {
            "plate_number": "MH14CD5678",
            "nickname": "Mumbai Truck 1",
            "make": "Ashok Leyland",
            "model": "Dost",
            "year": 2021,
            "vehicle_type": "truck",
            "fleet_group": "Mumbai Fleet",
            "device_id": "DEV-0002",
            "assigned_driver": "Suresh Patil",
        },
        {
            "plate_number": "KA05EF9012",
            "nickname": "Bangalore Van",
            "make": "Mahindra",
            "model": "Bolero Pickup",
            "year": 2023,
            "vehicle_type": "van",
            "fleet_group": "Bangalore Fleet",
            "device_id": "DEV-0003",
            "assigned_driver": "Anita Sharma",
        },
        {
            "plate_number": "DL01GH3456",
            "nickname": "Delhi Spare",
            "make": "Tata",
            "model": "Ace",
            "year": 2020,
            "vehicle_type": "van",
            "fleet_group": "Delhi Fleet",
            "device_id": "DEV-0004",
            "assigned_driver": None,
        },
    ]
    vehicle_ids: dict[str, object] = {}
    for v in vehicles:
        insert_fields = {
            "company_id": company_id,
            "plate_number": v["plate_number"],
            "nickname": v["nickname"],
            "make": v["make"],
            "model": v["model"],
            "year": v["year"],
            "vehicle_type": v["vehicle_type"],
            "fleet_group": v["fleet_group"],
            "device_id": v["device_id"],
            "status": "active",
            "created_at": now,
        }
        # Optional FK: omit entirely rather than write null — the schema requires
        # assigned_driver_id to be an objectId *when present*, not nullable.
        if v["assigned_driver"]:
            insert_fields["assigned_driver_id"] = driver_ids[v["assigned_driver"]]

        doc = await db.vehicles.find_one_and_update(
            {"company_id": company_id, "plate_number": v["plate_number"]},
            {
                "$setOnInsert": {
                    **insert_fields,
                    "updated_at": now,
                }
            },
            upsert=True,
            return_document=True,
        )
        vehicle_ids[v["plate_number"]] = doc["_id"]

    yesterday_start = SEED_ANCHOR
    trips = [
        {
            "plate_number": "MH12AB1234",
            "start_time": yesterday_start,
            "end_time": yesterday_start + timedelta(hours=1, minutes=15),
            "start_location": {"lat": 18.5204, "lng": 73.8567, "address": "Pune Warehouse"},
            "end_location": {"lat": 18.6298, "lng": 73.7997, "address": "Pimpri, Pune"},
            "distance_km": 24.5,
            "duration_minutes": 75,
            "stop_count": 1,
            "avg_speed_kmph": 32.0,
            "max_speed_kmph": 58.0,
        },
        {
            "plate_number": "MH12AB1234",
            "start_time": yesterday_start + timedelta(hours=3),
            "end_time": yesterday_start + timedelta(hours=3, minutes=40),
            "start_location": {"lat": 18.6298, "lng": 73.7997, "address": "Pimpri, Pune"},
            "end_location": {"lat": 18.5204, "lng": 73.8567, "address": "Pune Warehouse"},
            "distance_km": 22.1,
            "duration_minutes": 40,
            "stop_count": 0,
            "avg_speed_kmph": 33.0,
            "max_speed_kmph": 61.0,
        },
    ]
    for t in trips:
        plate = t.pop("plate_number")
        vehicle_id = vehicle_ids[plate]
        await db.trips.update_one(
            {"company_id": company_id, "vehicle_id": vehicle_id, "start_time": t["start_time"]},
            {"$setOnInsert": {"company_id": company_id, "vehicle_id": vehicle_id, "created_at": now, **t}},
            upsert=True,
        )

    alerts = [
        {
            "plate_number": "MH12AB1234",
            "alert_type": "speeding",
            "severity": "medium",
            "triggered_at": yesterday_start + timedelta(minutes=20),
            "location": {"lat": 18.55, "lng": 73.83},
            "details": "Recorded 78 km/h in a 60 km/h zone",
        },
        {
            "plate_number": "MH14CD5678",
            "alert_type": "low_fuel",
            "severity": "low",
            "triggered_at": SEED_ANCHOR + timedelta(hours=20),
            "location": {"lat": 19.076, "lng": 72.877},
            "details": "Fuel level dropped below 15%",
        },
    ]
    for a in alerts:
        plate = a.pop("plate_number")
        vehicle_id = vehicle_ids[plate]
        await db.alerts.update_one(
            {"company_id": company_id, "vehicle_id": vehicle_id, "triggered_at": a["triggered_at"]},
            {
                "$setOnInsert": {
                    "company_id": company_id,
                    "vehicle_id": vehicle_id,
                    "acknowledged": False,
                    "created_at": now,
                    **a,
                }
            },
            upsert=True,
        )

    maintenance_records = [
        {
            "plate_number": "MH12AB1234",
            "service_type": "oil_change",
            "service_date": SEED_ANCHOR - timedelta(days=45),
            "odometer_km": 18342.0,
            "cost": 2200.0,
            "notes": "Routine oil + filter change",
            "next_due_date": SEED_ANCHOR + timedelta(days=45),
            "next_due_odometer_km": 23000.0,
        },
        {
            "plate_number": "KA05EF9012",
            "service_type": "general_service",
            "service_date": SEED_ANCHOR - timedelta(days=200),
            "odometer_km": 9120.0,
            "cost": 5400.0,
            "notes": "General service, brake pads replaced",
            "next_due_date": SEED_ANCHOR + timedelta(days=5),
            "next_due_odometer_km": 15000.0,
        },
    ]
    for m in maintenance_records:
        plate = m.pop("plate_number")
        vehicle_id = vehicle_ids[plate]
        await db.maintenance_records.update_one(
            {"company_id": company_id, "vehicle_id": vehicle_id, "service_date": m["service_date"]},
            {"$setOnInsert": {"company_id": company_id, "vehicle_id": vehicle_id, "created_at": now, **m}},
            upsert=True,
        )

    await db.geofences.update_one(
        {"company_id": company_id, "name": "Mumbai Warehouse Zone"},
        {
            "$setOnInsert": {
                "company_id": company_id,
                "name": "Mumbai Warehouse Zone",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [72.870, 19.070],
                            [72.885, 19.070],
                            [72.885, 19.085],
                            [72.870, 19.085],
                            [72.870, 19.070],
                        ]
                    ],
                },
                "vehicle_ids": [vehicle_ids["MH12AB1234"], vehicle_ids["MH14CD5678"]],
                "fleet_group": "Mumbai Fleet",
                "active": True,
                "created_at": now,
            }
        },
        upsert=True,
    )

    admin_user = await db.users.find_one({"company_id": company_id, "email": "admin@cosmica-test.example"})
    session_doc = await db.chat_sessions.find_one_and_update(
        {"company_id": company_id, "user_id": admin_user["_id"], "status": "active"},
        {
            "$setOnInsert": {
                "company_id": company_id,
                "user_id": admin_user["_id"],
                "status": "active",
                "started_at": now,
                "last_active_at": now,
                "active_entities": {"vehicle_id": vehicle_ids["MH12AB1234"]},
            }
        },
        upsert=True,
        return_document=True,
    )
    sample_messages = [
        {"role": "user", "content": "Where is MH12AB1234 right now?", "intent": "GET_VEHICLE_LOCATION"},
        {
            "role": "assistant",
            "content": "MH12AB1234 is currently near Pimpri, Pune.",
            # no "intent" key — assistant turns aren't classified, and the schema requires
            # intent to be a string *when present* rather than accepting null.
        },
        {"role": "user", "content": "What's its speed?", "intent": "GET_VEHICLE_SPEED"},
    ]
    for i, m in enumerate(sample_messages):
        await db.chat_messages.update_one(
            {"session_id": session_doc["_id"], "content": m["content"]},
            {
                "$setOnInsert": {
                    "session_id": session_doc["_id"],
                    "company_id": company_id,
                    "created_at": now + timedelta(seconds=i),
                    **m,
                }
            },
            upsert=True,
        )

    documents = [
        {
            "title": "Geofencing Feature Guide",
            "source_type": "feature_guide",
            "version": "v1",
            "approved_pricing": False,
        },
        {
            "title": "How to Register a GPS Device",
            "source_type": "app_faq",
            "version": "v1",
            "approved_pricing": False,
        },
        {
            "title": "GPS Device Offline Troubleshooting",
            "source_type": "troubleshooting",
            "version": "v1",
            "approved_pricing": False,
        },
        {
            "title": "Data Retention Policy",
            "source_type": "policy",
            "version": "v2",
            "approved_pricing": False,
        },
        {
            "title": "Track91 Pricing Sheet",
            "source_type": "pricing",
            "version": "v3-approved",
            "approved_pricing": True,
        },
        {
            "title": "Draft Enterprise Pricing Notes",
            "source_type": "pricing",
            "version": "draft-2026-06",
            "approved_pricing": False,
        },
    ]
    for doc in documents:
        await db.documents_meta.update_one(
            {"title": doc["title"], "version": doc["version"]},
            {
                "$setOnInsert": {
                    "is_active": True,
                    "ingested_at": now,
                    **doc,
                }
            },
            upsert=True,
        )

    logger.info("Seed complete for company_id=%s", company_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed())

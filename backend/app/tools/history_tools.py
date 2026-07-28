"""MONGO_REPO tool handlers — thin wrappers around the repository layer (ADR 001). Every call
here goes through a repository method that requires company_id; none of these construct a raw
Mongo query themselves."""

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.db.repositories.alert_repository import AlertRepository
from app.db.repositories.driver_repository import DriverRepository
from app.db.repositories.geofence_repository import GeofenceRepository
from app.db.repositories.maintenance_repository import MaintenanceRepository
from app.db.repositories.trip_repository import TripRepository
from app.db.repositories.vehicle_repository import VehicleRepository


async def _vehicle_ids_for_fleet_group(db: AsyncIOMotorDatabase, company_id, params: dict) -> list | None:
    if "vehicle_id" in params or "fleet_group_ref" not in params:
        return None
    return await VehicleRepository(db).list_ids_by_fleet_group(company_id, params["fleet_group_ref"])


async def get_trip_history(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> list[dict]:
    repo = TripRepository(db)
    return await repo.find_trips(
        company_id, params["date_range"], vehicle_id=params.get("vehicle_id"), driver_id=params.get("driver_id")
    )


async def get_trip_summary(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> dict:
    repo = TripRepository(db)
    vehicle_ids = await _vehicle_ids_for_fleet_group(db, company_id, params)
    return await repo.summarize_trips(
        company_id, params["date_range"], vehicle_id=params.get("vehicle_id"), vehicle_ids=vehicle_ids
    )


async def get_alert_history(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> list[dict]:
    repo = AlertRepository(db)
    return await repo.find_alerts(
        company_id,
        params["date_range"],
        vehicle_id=params.get("vehicle_id"),
        driver_id=params.get("driver_id"),
        alert_type=params.get("alert_type"),
    )


async def get_maintenance_history(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> list[dict]:
    repo = MaintenanceRepository(db)
    return await repo.find_history(company_id, params["vehicle_id"], date_range=params.get("date_range"))


async def get_maintenance_due(params: dict, *, company_id, db: AsyncIOMotorDatabase, now, **_) -> list[dict]:
    repo = MaintenanceRepository(db)
    vehicle_ids = await _vehicle_ids_for_fleet_group(db, company_id, params)
    return await repo.find_due(company_id, now, vehicle_id=params.get("vehicle_id"), vehicle_ids=vehicle_ids)


async def get_driver_behavior_report(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> dict:
    repo = AlertRepository(db)
    counts = await repo.count_alerts_by_type(company_id, params["driver_id"], params["date_range"])
    return {"alert_counts": counts, "total_alerts": sum(counts.values())}


async def get_fuel_consumption_report(params: dict, **_) -> dict:
    """Honest gap, not a fabricated number: trips (app/db/schema_definitions.py) don't record
    fuel used, only distance/duration/speed — there's no real data to compute this report from
    in this pilot build. Returning a clear "not available" result rather than approximating
    consumption from distance, which would misrepresent unmeasured data as a real figure."""
    return {"available": False, "reason": "Fuel consumption is not tracked in trip records for this pilot build."}


async def get_geofence_list(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> list[dict]:
    repo = GeofenceRepository(db)
    return await repo.list_for_vehicle_or_group(
        company_id, vehicle_id=params.get("vehicle_id"), fleet_group=params.get("fleet_group_ref")
    )


async def get_vehicle_roster(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> list[dict]:
    repo = VehicleRepository(db)
    return await repo.list_by_company(company_id, fleet_group=params.get("fleet_group_ref"))


async def get_driver_roster(params: dict, *, company_id, db: AsyncIOMotorDatabase, **_) -> list[dict]:
    if "vehicle_id" in params:
        vehicle = await VehicleRepository(db).get_by_id(company_id, params["vehicle_id"])
        if not vehicle or not vehicle.get("assigned_driver_id"):
            return []
        driver = await DriverRepository(db).get_by_id(company_id, vehicle["assigned_driver_id"])
        return [driver] if driver else []
    return await DriverRepository(db).list_by_company(company_id)

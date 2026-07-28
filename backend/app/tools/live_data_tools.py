"""LIVE_API tool handlers — thin wrappers around FleetGPSClient. Never touch Mongo/Chroma for
the data itself, per the roadmap's live-data rule."""

from app.tools.fleet_gps_client import FleetGPSClient


async def get_vehicle_location(params: dict, *, gps_client: FleetGPSClient, now=None, **_) -> dict:
    return await gps_client.get_location(str(params["vehicle_id"]), now=now)


async def get_vehicle_speed(params: dict, *, gps_client: FleetGPSClient, now=None, **_) -> dict:
    return await gps_client.get_speed(str(params["vehicle_id"]), now=now)


async def get_vehicle_fuel_level(params: dict, *, gps_client: FleetGPSClient, now=None, **_) -> dict:
    return await gps_client.get_fuel_level(str(params["vehicle_id"]), now=now)


async def get_vehicle_health(params: dict, *, gps_client: FleetGPSClient, now=None, **_) -> dict:
    return await gps_client.get_health(str(params["vehicle_id"]), metric_type=params.get("metric_type"), now=now)


async def get_vehicle_ignition_status(params: dict, *, gps_client: FleetGPSClient, now=None, **_) -> dict:
    return await gps_client.get_ignition_status(str(params["vehicle_id"]), now=now)


async def get_fleet_live_status(params: dict, *, company_id, gps_client: FleetGPSClient, now=None, **_) -> dict:
    return await gps_client.get_fleet_live_status(str(company_id), fleet_group=params.get("fleet_group_ref"), now=now)

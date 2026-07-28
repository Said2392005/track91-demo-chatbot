"""
Fleet GPS client — interface + mock implementation, per the roadmap's non-negotiable rule:
live telemetry (location, speed, fuel, health) is NEVER stored in Mongo or Chroma, always
fetched live through this service layer. No real Track91/Fleet GPS API exists in this build
(confirmed at Phase 1 kickoff — mocked everywhere); a real adapter implementing the same
interface can be swapped in later without touching any tool/router code.
"""

import random
from abc import ABC, abstractmethod
from datetime import datetime, timezone


class FleetGPSClient(ABC):
    @abstractmethod
    async def get_location(self, vehicle_id: str, now: datetime | None = None) -> dict: ...

    @abstractmethod
    async def get_speed(self, vehicle_id: str, now: datetime | None = None) -> dict: ...

    @abstractmethod
    async def get_fuel_level(self, vehicle_id: str, now: datetime | None = None) -> dict: ...

    @abstractmethod
    async def get_health(
        self, vehicle_id: str, metric_type: str | None = None, now: datetime | None = None
    ) -> dict: ...

    @abstractmethod
    async def get_ignition_status(self, vehicle_id: str, now: datetime | None = None) -> dict: ...

    @abstractmethod
    async def get_fleet_live_status(
        self, company_id: str, fleet_group: str | None = None, now: datetime | None = None
    ) -> dict: ...


class MockFleetGPSClient(FleetGPSClient):
    """Deterministic pseudo-random data, seeded per (vehicle_id, call-type) so repeated calls
    for the same vehicle return stable values within and across calls — plausible for demoing
    and testing without being pure noise. Never persisted anywhere; the caller (tool handlers,
    app/router/registry.py) is responsible for keeping it that way."""

    @staticmethod
    def _rng(*seed_parts: str) -> random.Random:
        return random.Random("|".join(str(p) for p in seed_parts))

    @staticmethod
    def _as_of(now: datetime | None) -> str:
        return (now or datetime.now(timezone.utc)).isoformat()

    async def get_location(self, vehicle_id: str, now: datetime | None = None) -> dict:
        rng = self._rng(vehicle_id, "location")
        return {
            "lat": round(rng.uniform(8.0, 28.0), 4),
            "lng": round(rng.uniform(72.0, 88.0), 4),
            "as_of": self._as_of(now),
        }

    async def get_speed(self, vehicle_id: str, now: datetime | None = None) -> dict:
        rng = self._rng(vehicle_id, "speed")
        return {"speed_kmph": round(rng.uniform(0, 90), 1), "as_of": self._as_of(now)}

    async def get_fuel_level(self, vehicle_id: str, now: datetime | None = None) -> dict:
        rng = self._rng(vehicle_id, "fuel")
        return {"fuel_percent": round(rng.uniform(5, 100), 1), "as_of": self._as_of(now)}

    async def get_health(
        self, vehicle_id: str, metric_type: str | None = None, now: datetime | None = None
    ) -> dict:
        rng = self._rng(vehicle_id, "health")
        result = {
            "engine_temperature_c": round(rng.uniform(70, 110), 1),
            "battery_voltage": round(rng.uniform(11.5, 14.5), 2),
            "warnings": [] if rng.random() > 0.2 else ["check_engine"],
            "as_of": self._as_of(now),
        }
        if metric_type == "engine_temperature":
            return {"engine_temperature_c": result["engine_temperature_c"], "as_of": result["as_of"]}
        if metric_type == "battery_voltage":
            return {"battery_voltage": result["battery_voltage"], "as_of": result["as_of"]}
        return result

    async def get_ignition_status(self, vehicle_id: str, now: datetime | None = None) -> dict:
        rng = self._rng(vehicle_id, "ignition")
        ignition = rng.choice(["on", "off"])
        return {
            "ignition": ignition,
            "moving": ignition == "on" and rng.random() > 0.3,
            "as_of": self._as_of(now),
        }

    async def get_fleet_live_status(
        self, company_id: str, fleet_group: str | None = None, now: datetime | None = None
    ) -> dict:
        rng = self._rng(company_id, fleet_group or "", "fleet_status")
        total = rng.randint(3, 20)
        moving = rng.randint(0, total)
        return {
            "total_vehicles": total,
            "moving": moving,
            "idle": total - moving,
            "as_of": self._as_of(now),
        }

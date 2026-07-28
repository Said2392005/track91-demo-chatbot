"""
Tool registry — the intent -> (subsystem, handler) mapping. One entry per MVP intent from
app/core/taxonomy.py; backlog intents (CREATE_GEOFENCE, etc.) and NONE-subsystem meta intents
deliberately have no entry here — router.py handles those outcomes before ever consulting this
registry.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.tools import history_tools, kb_tools, live_data_tools
from app.tools.general_knowledge import general_knowledge

ToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    subsystem: str
    handler: ToolHandler


TOOL_REGISTRY: dict[str, ToolSpec] = {
    # LIVE_API
    "GET_VEHICLE_LOCATION": ToolSpec("get_vehicle_location", "LIVE_API", live_data_tools.get_vehicle_location),
    "GET_VEHICLE_SPEED": ToolSpec("get_vehicle_speed", "LIVE_API", live_data_tools.get_vehicle_speed),
    "GET_VEHICLE_FUEL_LEVEL": ToolSpec("get_vehicle_fuel_level", "LIVE_API", live_data_tools.get_vehicle_fuel_level),
    "GET_VEHICLE_HEALTH": ToolSpec("get_vehicle_health", "LIVE_API", live_data_tools.get_vehicle_health),
    "GET_VEHICLE_IGNITION_STATUS": ToolSpec(
        "get_vehicle_ignition_status", "LIVE_API", live_data_tools.get_vehicle_ignition_status
    ),
    "GET_FLEET_LIVE_STATUS": ToolSpec("get_fleet_live_status", "LIVE_API", live_data_tools.get_fleet_live_status),
    # MONGO_REPO
    "GET_TRIP_HISTORY": ToolSpec("get_trip_history", "MONGO_REPO", history_tools.get_trip_history),
    "GET_TRIP_SUMMARY": ToolSpec("get_trip_summary", "MONGO_REPO", history_tools.get_trip_summary),
    "GET_ALERT_HISTORY": ToolSpec("get_alert_history", "MONGO_REPO", history_tools.get_alert_history),
    "GET_MAINTENANCE_HISTORY": ToolSpec(
        "get_maintenance_history", "MONGO_REPO", history_tools.get_maintenance_history
    ),
    "GET_MAINTENANCE_DUE": ToolSpec("get_maintenance_due", "MONGO_REPO", history_tools.get_maintenance_due),
    "GET_DRIVER_BEHAVIOR_REPORT": ToolSpec(
        "get_driver_behavior_report", "MONGO_REPO", history_tools.get_driver_behavior_report
    ),
    "GET_FUEL_CONSUMPTION_REPORT": ToolSpec(
        "get_fuel_consumption_report", "MONGO_REPO", history_tools.get_fuel_consumption_report
    ),
    "GET_GEOFENCE_LIST": ToolSpec("get_geofence_list", "MONGO_REPO", history_tools.get_geofence_list),
    "GET_VEHICLE_ROSTER": ToolSpec("get_vehicle_roster", "MONGO_REPO", history_tools.get_vehicle_roster),
    "GET_DRIVER_ROSTER": ToolSpec("get_driver_roster", "MONGO_REPO", history_tools.get_driver_roster),
    # RAG
    "EXPLAIN_FEATURE": ToolSpec("explain_feature", "RAG", kb_tools.explain_feature),
    "EXPLAIN_ALERT_TYPE": ToolSpec("explain_alert_type", "RAG", kb_tools.explain_alert_type),
    "APP_FAQ": ToolSpec("app_faq", "RAG", kb_tools.app_faq),
    "TROUBLESHOOTING_DEVICE": ToolSpec("troubleshooting_device", "RAG", kb_tools.troubleshooting_device),
    "POLICY_QUESTION": ToolSpec("policy_question", "RAG", kb_tools.policy_question),
    "PRICING": ToolSpec("pricing", "RAG", kb_tools.pricing),
    # GENERAL_FALLBACK
    "GENERAL_KNOWLEDGE": ToolSpec("general_knowledge", "GENERAL_FALLBACK", general_knowledge),
}

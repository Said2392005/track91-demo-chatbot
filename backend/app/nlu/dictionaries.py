"""Synonym dictionaries for enum-valued entities (entity-taxonomy.md). Closed sets, defined
fully in Phase 3's schema (app/db/schema_definitions.py) — these are just the surface-form
synonyms the classifier/extractor maps onto those canonical enum values."""

ALERT_TYPE_SYNONYMS: dict[str, list[str]] = {
    "speeding": ["speeding", "over speed", "overspeeding", "too fast", "over the limit"],
    "harsh_braking": ["harsh braking", "hard braking", "sudden braking", "harsh brake"],
    "harsh_acceleration": ["harsh acceleration", "hard acceleration", "rapid acceleration"],
    "idle": ["idling", "idle time", "idle alert", "idling too long"],
    "panic": ["panic", "sos", "emergency button", "panic button", "distress"],
    "geofence_entry": ["geofence entry", "entered geofence", "entering geofence", "geofence in"],
    "geofence_exit": ["geofence exit", "exited geofence", "exiting geofence", "geofence out"],
    "low_fuel": ["low fuel", "fuel low", "fuel level low", "fuel warning"],
    "device_offline": ["device offline", "gps offline", "not connected", "disconnected", "offline"],
    "maintenance_due": ["maintenance due", "service due", "service reminder"],
}

METRIC_TYPE_SYNONYMS: dict[str, list[str]] = {
    "speed": ["speed", "how fast", "km/h", "kmph"],
    "fuel": ["fuel", "petrol", "diesel", "fuel level"],
    "odometer": ["odometer", "mileage", "distance reading"],
    "engine_temperature": ["engine temperature", "engine temp", "overheating"],
    "battery_voltage": ["battery voltage", "battery level", "battery"],
}

REPORT_TYPE_SYNONYMS: dict[str, list[str]] = {
    "trip_summary": ["trip summary", "trip report"],
    "fuel_report": ["fuel report", "fuel efficiency report", "fuel consumption report"],
    "driver_scorecard": ["driver scorecard", "driving score", "driver score", "behavior report"],
    "maintenance_report": ["maintenance report", "service report"],
}

PLAN_TIER_SYNONYMS: dict[str, list[str]] = {
    "Starter": ["starter plan", "starter"],
    "Pro": ["pro plan", "pro tier", "professional plan"],
    "Enterprise": ["enterprise plan", "enterprise tier"],
}


def match_dictionary(text: str, synonyms: dict[str, list[str]]) -> str | None:
    lowered = text.lower()
    for canonical, phrases in synonyms.items():
        for phrase in phrases:
            if phrase in lowered:
                return canonical
    return None

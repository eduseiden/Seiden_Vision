from __future__ import annotations

import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from analyzers.base import Analyzer
from version import SCHEMA_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_") or "environment_source"


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _dimension_score(value: float, comfortable_min: float, comfortable_max: float, outer_min: float, outer_max: float) -> float:
    if comfortable_min <= value <= comfortable_max:
        return 50.0
    if value < comfortable_min:
        if value <= outer_min:
            return 0.0
        return 50.0 * (value - outer_min) / (comfortable_min - outer_min)
    if value >= outer_max:
        return 0.0
    return 50.0 * (outer_max - value) / (outer_max - comfortable_max)


class EnvironmentalAnalyzer(Analyzer):
    """Reconhece e normaliza medições ambientais provenientes do Bridge."""

    name = "environmental"

    def can_handle(self, payload: dict[str, Any]) -> bool:
        if payload.get("source") != "seiden_bridge":
            return False
        if payload.get("event_type") != "mqtt.message_received":
            return False
        data = payload.get("data")
        return isinstance(data, dict) and _as_float(data.get("temperature")) is not None and _as_float(data.get("humidity")) is not None

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.can_handle(payload):
            return None

        data = payload["data"]
        raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
        connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
        temperature = _as_float(data.get("temperature"))
        humidity = _as_float(data.get("humidity"))
        if temperature is None or humidity is None:
            return None

        unit = str(data.get("temperature_unit_convert") or "celsius").strip().lower()
        if unit in {"fahrenheit", "f", "°f"}:
            temperature_c = (temperature - 32.0) * 5.0 / 9.0
        else:
            temperature_c = temperature

        topic = str(payload.get("topic") or raw.get("topic") or "").strip()
        topic_tail = topic.rsplit("/", 1)[-1].strip() if topic else "Environmental Sensor"
        source_name = topic_tail or "Environmental Sensor"
        source_id = _slug(source_name)

        location_name = re.sub(r"(?i)^term[oô]metro\s*", "", source_name).strip() or source_name
        location_id = _slug(location_name)

        temperature_score = _dimension_score(temperature_c, 21.0, 25.0, 18.0, 28.0)
        humidity_score = _dimension_score(humidity, 40.0, 60.0, 30.0, 70.0)
        score = round(temperature_score + humidity_score, 1)

        temp_uncomfortable = temperature_c < 18.0 or temperature_c > 28.0
        humidity_uncomfortable = humidity < 30.0 or humidity > 70.0
        if temp_uncomfortable or humidity_uncomfortable:
            condition = "uncomfortable"
        elif 21.0 <= temperature_c <= 25.0 and 40.0 <= humidity <= 60.0:
            condition = "comfortable"
        else:
            condition = "attention"

        source_event_id = str(payload.get("event_id") or "").strip() or None
        timestamp = str(payload.get("timestamp") or data.get("last_seen") or _utc_now())
        return {
            "schema_version": SCHEMA_VERSION,
            "event_id": str(uuid.uuid4()),
            "event_type": "environment.observation",
            "source": "seiden_vision",
            "timestamp": timestamp,
            "correlation": {
                "source_event_id": source_event_id,
            },
            "origin": {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": "environment_sensor",
                "location_id": location_id,
                "location_name": location_name,
                "connection_id": payload.get("connection_id") or connection.get("id"),
                "connector": payload.get("connector") or connection.get("connector"),
                "topic": topic,
            },
            "measurements": {
                "temperature": {
                    "value": round(temperature_c, 2),
                    "unit": "celsius",
                    "original_value": temperature,
                    "original_unit": unit,
                },
                "humidity": {
                    "value": round(humidity, 2),
                    "unit": "percent",
                },
            },
            "analysis": {
                "analyzer": self.name,
                "condition": condition,
                "comfort_score": score,
                "confidence": 1.0,
                "ruleset": "seiden_environmental_comfort_v1",
            },
            "source_health": {
                "battery_pct": _as_float(data.get("battery")),
                "linkquality": _as_float(data.get("linkquality")),
                "last_seen": data.get("last_seen"),
            },
            "status": "success",
        }

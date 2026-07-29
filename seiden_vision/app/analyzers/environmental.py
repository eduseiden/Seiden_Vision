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


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first_text(*values: Any) -> str | None:
    for value in values:
        text = _clean_text(value)
        if text is not None:
            return text
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
    """Reconhece e normaliza medições ambientais provenientes do Bridge.

    A identidade cadastrada no Environmental Source Registry do Bridge é sempre
    priorizada. O tópico MQTT só é usado como fallback para eventos legados.
    """

    name = "environmental"

    @staticmethod
    def _parts(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
        connection = payload.get("connection") if isinstance(payload.get("connection"), dict) else {}
        environment = payload.get("environment") if isinstance(payload.get("environment"), dict) else {}
        measurements = environment.get("measurements") if isinstance(environment.get("measurements"), dict) else {}
        return data, raw, connection, measurements

    @staticmethod
    def _temperature(payload: dict[str, Any], data: dict[str, Any], measurements: dict[str, Any]) -> tuple[float | None, str]:
        canonical = _as_float(measurements.get("temperature_c"))
        if canonical is None:
            canonical = _as_float(payload.get("temperature_c"))
        if canonical is not None:
            return canonical, "celsius"

        raw_temperature = _as_float(data.get("temperature"))
        unit = str(data.get("temperature_unit_convert") or "celsius").strip().lower()
        if raw_temperature is None:
            return None, unit
        if unit in {"fahrenheit", "f", "°f"}:
            return (raw_temperature - 32.0) * 5.0 / 9.0, unit
        return raw_temperature, unit

    @staticmethod
    def _humidity(payload: dict[str, Any], data: dict[str, Any], measurements: dict[str, Any]) -> float | None:
        return (
            _as_float(measurements.get("humidity_pct"))
            if _as_float(measurements.get("humidity_pct")) is not None
            else _as_float(payload.get("humidity_pct"))
            if _as_float(payload.get("humidity_pct")) is not None
            else _as_float(data.get("humidity"))
        )

    def can_handle(self, payload: dict[str, Any]) -> bool:
        if payload.get("source") != "seiden_bridge":
            return False
        if payload.get("event_type") != "mqtt.message_received":
            return False
        data, _raw, _connection, measurements = self._parts(payload)
        temperature, _unit = self._temperature(payload, data, measurements)
        humidity = self._humidity(payload, data, measurements)
        return temperature is not None and humidity is not None

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.can_handle(payload):
            return None

        data, raw, connection, measurements = self._parts(payload)
        environment = payload.get("environment") if isinstance(payload.get("environment"), dict) else {}

        temperature_c, original_unit = self._temperature(payload, data, measurements)
        humidity = self._humidity(payload, data, measurements)
        if temperature_c is None or humidity is None:
            return None

        original_temperature = _as_float(data.get("temperature"))
        if original_temperature is None:
            original_temperature = temperature_c

        topic = str(payload.get("topic") or raw.get("topic") or "").strip()
        topic_tail = topic.rsplit("/", 1)[-1].strip() if topic else "Environmental Sensor"

        # Registry do Bridge > campos canônicos no evento > fallback legado pelo tópico.
        source_name = _first_text(environment.get("source_name"), payload.get("source_name"), topic_tail) or "Environmental Sensor"
        source_id = _first_text(environment.get("source_id"), payload.get("source_id")) or _slug(source_name)

        fallback_location_name = re.sub(r"(?i)^term[oô]metro[ _-]*", "", source_name).strip() or source_name
        location_name = _first_text(environment.get("location_name"), payload.get("location_name"), fallback_location_name) or fallback_location_name
        location_id = _first_text(environment.get("location_id"), payload.get("location_id")) or _slug(location_name)

        description = _first_text(environment.get("description"), payload.get("description"))
        asset_id = _first_text(environment.get("asset_id"), payload.get("asset_id"))
        asset_name = _first_text(environment.get("asset_name"), payload.get("asset_name"))
        profile_id = _first_text(environment.get("profile_id"), payload.get("profile_id"), "human_indoor") or "human_indoor"

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

        battery_pct = _as_float(measurements.get("battery_pct"))
        if battery_pct is None:
            battery_pct = _as_float(payload.get("battery_pct"))
        if battery_pct is None:
            battery_pct = _as_float(data.get("battery"))

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
                "description": description,
                "location_id": location_id,
                "location_name": location_name,
                "asset_id": asset_id,
                "asset_name": asset_name,
                "profile_id": profile_id,
                "identity_source": "bridge_registry" if environment else "mqtt_topic_fallback",
                "connection_id": payload.get("connection_id") or connection.get("id"),
                "connector": payload.get("connector") or connection.get("connector"),
                "topic": topic,
            },
            "measurements": {
                "temperature": {
                    "value": round(temperature_c, 2),
                    "unit": "celsius",
                    "original_value": original_temperature,
                    "original_unit": original_unit,
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
                "profile_id": profile_id,
            },
            "source_health": {
                "battery_pct": battery_pct,
                "linkquality": _as_float(data.get("linkquality")),
                "last_seen": data.get("last_seen"),
            },
            "status": "success",
        }

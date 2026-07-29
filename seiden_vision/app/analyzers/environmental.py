from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class MetricBand:
    optimal_min: float
    optimal_max: float
    attention_min: float
    attention_max: float
    critical_min: float
    critical_max: float
    weight: float = 1.0


@dataclass(frozen=True)
class EnvironmentalProfile:
    profile_id: str
    label: str
    analysis_type: str
    temperature: MetricBand
    humidity: MetricBand | None
    ruleset: str


PROFILES: dict[str, EnvironmentalProfile] = {
    "human_indoor": EnvironmentalProfile(
        profile_id="human_indoor",
        label="Conforto humano interno",
        analysis_type="human_comfort",
        temperature=MetricBand(21.0, 25.0, 18.0, 28.0, 15.0, 32.0, 0.5),
        humidity=MetricBand(40.0, 60.0, 30.0, 70.0, 20.0, 80.0, 0.5),
        ruleset="seiden_environmental_profile_human_indoor_v1",
    ),
    "human_outdoor": EnvironmentalProfile(
        profile_id="human_outdoor",
        label="Ambiente externo",
        analysis_type="informational",
        temperature=MetricBand(18.0, 28.0, 10.0, 35.0, 0.0, 42.0, 0.7),
        humidity=MetricBand(35.0, 75.0, 20.0, 90.0, 10.0, 100.0, 0.3),
        ruleset="seiden_environmental_profile_human_outdoor_v1",
    ),
    "refrigerator": EnvironmentalProfile(
        profile_id="refrigerator",
        label="Geladeira",
        analysis_type="environmental_compliance",
        temperature=MetricBand(2.0, 5.0, 0.0, 8.0, -2.0, 10.0, 1.0),
        humidity=None,
        ruleset="seiden_environmental_profile_refrigerator_v1",
    ),
    "freezer": EnvironmentalProfile(
        profile_id="freezer",
        label="Freezer",
        analysis_type="environmental_compliance",
        temperature=MetricBand(-22.0, -18.0, -25.0, -15.0, -30.0, -12.0, 1.0),
        humidity=None,
        ruleset="seiden_environmental_profile_freezer_v1",
    ),
    "wine_cellar": EnvironmentalProfile(
        profile_id="wine_cellar",
        label="Adega de vinhos",
        analysis_type="environmental_compliance",
        temperature=MetricBand(12.0, 16.0, 10.0, 18.0, 7.0, 22.0, 0.6),
        humidity=MetricBand(55.0, 75.0, 45.0, 80.0, 35.0, 90.0, 0.4),
        ruleset="seiden_environmental_profile_wine_cellar_v1",
    ),
    "beer_cooler": EnvironmentalProfile(
        profile_id="beer_cooler",
        label="Cervejeira",
        analysis_type="environmental_compliance",
        temperature=MetricBand(2.0, 6.0, 0.0, 8.0, -2.0, 12.0, 1.0),
        humidity=None,
        ruleset="seiden_environmental_profile_beer_cooler_v1",
    ),
}


def _metric_score(value: float, band: MetricBand) -> float:
    """Converte uma medição em score 0..100 com transições contínuas."""
    if band.optimal_min <= value <= band.optimal_max:
        return 100.0

    if value < band.optimal_min:
        if value <= band.critical_min:
            return 0.0
        if value < band.attention_min:
            span = band.attention_min - band.critical_min
            return 50.0 * (value - band.critical_min) / span if span else 0.0
        span = band.optimal_min - band.attention_min
        return 70.0 + 30.0 * (value - band.attention_min) / span if span else 70.0

    if value >= band.critical_max:
        return 0.0
    if value > band.attention_max:
        span = band.critical_max - band.attention_max
        return 50.0 * (band.critical_max - value) / span if span else 0.0
    span = band.attention_max - band.optimal_max
    return 70.0 + 30.0 * (band.attention_max - value) / span if span else 70.0


def _condition_from_score(score: float) -> str:
    if score >= 85.0:
        return "comfortable"
    if score >= 70.0:
        return "attention"
    if score >= 50.0:
        return "uncomfortable"
    return "critical"


def _operational_state(condition: str, analysis_type: str) -> str:
    if analysis_type == "environmental_compliance":
        return {
            "comfortable": "optimal",
            "attention": "attention",
            "uncomfortable": "out_of_range",
            "critical": "critical",
        }[condition]
    if analysis_type == "informational":
        return {
            "comfortable": "within_reference",
            "attention": "attention",
            "uncomfortable": "outside_reference",
            "critical": "extreme",
        }[condition]
    return condition


def _reason_codes(temperature: float, humidity: float | None, profile: EnvironmentalProfile) -> list[str]:
    reasons: list[str] = []

    def append_metric(metric: str, value: float, band: MetricBand) -> None:
        if value < band.critical_min:
            reasons.append(f"{metric}_below_critical_range")
        elif value > band.critical_max:
            reasons.append(f"{metric}_above_critical_range")
        elif value < band.attention_min:
            reasons.append(f"{metric}_below_attention_range")
        elif value > band.attention_max:
            reasons.append(f"{metric}_above_attention_range")
        elif value < band.optimal_min:
            reasons.append(f"{metric}_below_optimal_range")
        elif value > band.optimal_max:
            reasons.append(f"{metric}_above_optimal_range")

    append_metric("temperature", temperature, profile.temperature)
    if humidity is not None and profile.humidity is not None:
        append_metric("humidity", humidity, profile.humidity)
    return reasons or ["within_optimal_range"]


class EnvironmentalAnalyzer(Analyzer):
    """Normaliza medições ambientais e aplica o perfil definido na Bridge."""

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
        for value in (measurements.get("humidity_pct"), payload.get("humidity_pct"), data.get("humidity")):
            parsed = _as_float(value)
            if parsed is not None:
                return parsed
        return None

    def can_handle(self, payload: dict[str, Any]) -> bool:
        if payload.get("source") != "seiden_bridge":
            return False
        if payload.get("event_type") != "mqtt.message_received":
            return False
        data, _raw, _connection, measurements = self._parts(payload)
        temperature, _unit = self._temperature(payload, data, measurements)
        return temperature is not None

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        if not self.can_handle(payload):
            return None

        data, raw, connection, measurements = self._parts(payload)
        environment = payload.get("environment") if isinstance(payload.get("environment"), dict) else {}

        temperature_c, original_unit = self._temperature(payload, data, measurements)
        humidity = self._humidity(payload, data, measurements)
        if temperature_c is None:
            return None

        original_temperature = _as_float(data.get("temperature"))
        if original_temperature is None:
            original_temperature = temperature_c

        topic = str(payload.get("topic") or raw.get("topic") or "").strip()
        topic_tail = topic.rsplit("/", 1)[-1].strip() if topic else "Environmental Sensor"

        source_name = _first_text(environment.get("source_name"), payload.get("source_name"), topic_tail) or "Environmental Sensor"
        source_id = _first_text(environment.get("source_id"), payload.get("source_id")) or _slug(source_name)

        fallback_location_name = re.sub(r"(?i)^term[oô]metro[ _-]*", "", source_name).strip() or source_name
        location_name = _first_text(environment.get("location_name"), payload.get("location_name"), fallback_location_name) or fallback_location_name
        location_id = _first_text(environment.get("location_id"), payload.get("location_id")) or _slug(location_name)

        description = _first_text(environment.get("description"), payload.get("description"))
        asset_id = _first_text(environment.get("asset_id"), payload.get("asset_id"))
        asset_name = _first_text(environment.get("asset_name"), payload.get("asset_name"))
        requested_profile_id = _first_text(environment.get("profile_id"), payload.get("profile_id"), "human_indoor") or "human_indoor"
        profile = PROFILES.get(requested_profile_id)
        profile_fallback = profile is None
        if profile is None:
            profile = PROFILES["human_indoor"]

        metric_scores: dict[str, float] = {
            "temperature": round(_metric_score(temperature_c, profile.temperature), 2)
        }
        weighted_total = metric_scores["temperature"] * profile.temperature.weight
        total_weight = profile.temperature.weight

        if profile.humidity is not None and humidity is not None:
            metric_scores["humidity"] = round(_metric_score(humidity, profile.humidity), 2)
            weighted_total += metric_scores["humidity"] * profile.humidity.weight
            total_weight += profile.humidity.weight

        score = round(weighted_total / total_weight, 1) if total_weight else 0.0
        condition = _condition_from_score(score)
        reasons = _reason_codes(temperature_c, humidity, profile)
        if profile_fallback:
            reasons.insert(0, "unknown_profile_fallback_human_indoor")

        battery_pct = _as_float(measurements.get("battery_pct"))
        if battery_pct is None:
            battery_pct = _as_float(payload.get("battery_pct"))
        if battery_pct is None:
            battery_pct = _as_float(data.get("battery"))

        source_event_id = str(payload.get("event_id") or "").strip() or None
        timestamp = str(payload.get("timestamp") or data.get("last_seen") or _utc_now())
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "event_id": str(uuid.uuid4()),
            "event_type": "environment.observation",
            "source": "seiden_vision",
            "timestamp": timestamp,
            "correlation": {"source_event_id": source_event_id},
            "origin": {
                "source_id": source_id,
                "source_name": source_name,
                "source_type": "environment_sensor",
                "description": description,
                "location_id": location_id,
                "location_name": location_name,
                "asset_id": asset_id,
                "asset_name": asset_name,
                "profile_id": requested_profile_id,
                "resolved_profile_id": profile.profile_id,
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
            },
            "analysis": {
                "analyzer": self.name,
                "analysis_type": profile.analysis_type,
                "condition": condition,
                "operational_state": _operational_state(condition, profile.analysis_type),
                "environmental_score": score,
                "comfort_score": score,
                "metric_scores": metric_scores,
                "confidence": 1.0,
                "ruleset": profile.ruleset,
                "profile_id": requested_profile_id,
                "resolved_profile_id": profile.profile_id,
                "profile_label": profile.label,
                "profile_fallback": profile_fallback,
                "reason_codes": reasons,
            },
            "source_health": {
                "battery_pct": battery_pct,
                "linkquality": _as_float(data.get("linkquality")),
                "last_seen": data.get("last_seen"),
            },
            "status": "success",
        }
        if humidity is not None:
            result["measurements"]["humidity"] = {
                "value": round(humidity, 2),
                "unit": "percent",
            }
        return result

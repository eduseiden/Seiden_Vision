from __future__ import annotations

from typing import Any


def _bool_value(data: dict[str, Any] | None) -> bool | None:
    if not data or data.get("value") is None:
        return None
    return bool(data.get("value"))


def enrich_result(result: dict[str, Any], *, min_brightness: float, min_sharpness: float) -> dict[str, Any]:
    """Add provider-independent operational intelligence to a normalized result."""
    enriched = dict(result)
    quality = dict(enriched.get("quality") or {})
    brightness = float(quality.get("brightness") or 0.0)
    sharpness = float(quality.get("sharpness") or 0.0)
    face_count = int(enriched.get("face_count") or 0)

    score = round((brightness + sharpness) / 2.0, 2) if face_count else 0.0
    reasons: list[str] = []
    severity = "ok"

    if face_count == 0:
        severity = "critical"
        reasons.append("Nenhuma face detectada")
    elif face_count > 1:
        severity = "warning"
        reasons.append(f"Múltiplas faces detectadas ({face_count})")

    if face_count and brightness < min_brightness:
        severity = "warning" if severity == "ok" else severity
        reasons.append(f"Luminosidade abaixo do mínimo ({brightness:.1f} < {min_brightness:.1f})")
    if face_count and sharpness < min_sharpness:
        severity = "warning" if severity == "ok" else severity
        reasons.append(f"Nitidez abaixo do mínimo ({sharpness:.1f} < {min_sharpness:.1f})")

    if _bool_value(enriched.get("face_occluded")) is True:
        severity = "warning" if severity == "ok" else severity
        reasons.append("Face parcialmente ocluída")
    if _bool_value(enriched.get("eyes_open")) is False:
        reasons.append("Olhos fechados")

    enriched["operational"] = {
        "quality_score": score,
        "quality_status": "good" if severity == "ok" else "attention",
        "alert_level": severity,
        "alert": bool(reasons),
        "alert_reasons": reasons,
    }
    return enriched

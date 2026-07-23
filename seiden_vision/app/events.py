from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from version import SCHEMA_VERSION


def build_analysis_event(record: dict[str, Any], job: Any) -> dict[str, Any]:
    result = record.get("result") or {}
    quality = result.get("quality_evaluation") or result.get("operational") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": record.get("event_id"),
        "event_type": "vision.analysis_completed",
        "source": "seiden_vision",
        "timestamp": record.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "correlation": {
            "source_event_id": getattr(job, "source_event_id", None),
            "capture_id": getattr(job, "capture_id", None),
        },
        "origin": {
            "source_id": getattr(job, "source_id", None) or record.get("source"),
            "source_name": record.get("source"),
            "source_type": getattr(job, "source_type", None) or "reader",
            "device_id": getattr(job, "device_id", None),
            "location_id": getattr(job, "location_id", None),
        },
        "subject": {
            "person_id": getattr(job, "person_id", None),
            "person_name": record.get("person"),
        },
        "analysis": {
            "provider": record.get("provider"),
            "region": result.get("region"),
            "request_id": result.get("request_id"),
            "face_count": record.get("face_count", 0),
            "dominant_emotion": record.get("dominant_emotion"),
            "confidence": record.get("confidence"),
            "emotions": result.get("emotions") or {},
            "quality": result.get("quality") or {},
            "attributes": {
                key: result.get(key) for key in (
                    "pose", "age_range", "gender", "smile", "eyes_open",
                    "mouth_open", "eyeglasses", "sunglasses", "beard",
                    "mustache", "face_occluded", "bounding_box"
                )
            },
        },
        "quality": quality,
        "media": {
            "image_url": record.get("image_url"),
            "image_hash": record.get("image_hash"),
            "retained_path": record.get("retained_path"),
        },
        "processing": {
            "download_ms": record.get("download_ms"),
            "provider_ms": record.get("processing_ms"),
            "database_ms": record.get("database_ms"),
            "home_assistant_publish_ms": record.get("ha_publish_ms"),
            "total_ms": record.get("total_ms"),
        },
        "status": record.get("status"),
    }

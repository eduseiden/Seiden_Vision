from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


OPTIONS_PATH = Path("/data/options.json")
CONFIG_DIR = Path("/config")
DB_PATH = CONFIG_DIR / "seiden_vision.db"
IMAGES_DIR = CONFIG_DIR / "images"


@dataclass(frozen=True)
class Settings:
    log_level: str = "info"
    provider: str = "mock"
    minimum_confidence: int = 70
    duplicate_window_minutes: int = 1440
    download_timeout_seconds: int = 10
    maximum_image_size_mb: int = 5
    retain_images: bool = False
    history_retention_days: int = 90
    publish_to_home_assistant: bool = True
    source_enabled: bool = True
    source_name: str = "Entrada Principal"
    source_entity_id: str = "sensor.seiden_last_person"
    source_photo_attribute: str = "photo_url"
    poll_interval_seconds: int = 3
    aws_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_max_analyses_per_day: int = 1000
    aws_store_raw_response: bool = True
    aws_connect_timeout_seconds: int = 5
    aws_read_timeout_seconds: int = 20
    aws_max_attempts: int = 3
    quality_min_brightness: int = 35
    quality_min_sharpness: int = 40
    aws_price_per_1000_images: float = 1.0
    management_timezone: str = "America/Sao_Paulo"
    management_trend_days: int = 14
    person_event_cooldown_seconds: int = 10
    image_retention_days: int = 30
    max_stored_images: int = 5000
    cleanup_interval_hours: int = 6
    aws_monthly_budget_usd: float = 5.0
    source_inactivity_minutes: int = 30
    api_key: str = ""
    webhook_enabled: bool = False
    webhook_url: str = ""
    webhook_api_key: str = ""
    webhook_timeout_seconds: int = 10

    @property
    def supervisor_token(self) -> str:
        return os.environ.get("SUPERVISOR_TOKEN", "")

    @property
    def aws_configured(self) -> bool:
        return bool(self.aws_access_key_id.strip() and self.aws_secret_access_key.strip())

    @property
    def masked_access_key(self) -> str:
        key = self.aws_access_key_id.strip()
        if not key:
            return "não configurada"
        if len(key) <= 8:
            return "*" * len(key)
        return f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"


def _load_raw_options() -> dict[str, Any]:
    if not OPTIONS_PATH.exists():
        return {}
    try:
        return json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def load_settings() -> Settings:
    raw = _load_raw_options()
    defaults = Settings()
    values: dict[str, Any] = {}
    for field_name in Settings.__dataclass_fields__:
        if field_name == "supervisor_token":
            continue
        values[field_name] = raw.get(field_name, getattr(defaults, field_name))
    return Settings(**values)

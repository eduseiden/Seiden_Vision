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
    maximum_image_size_mb: int = 8
    retain_images: bool = False
    history_retention_days: int = 90
    publish_to_home_assistant: bool = True
    source_enabled: bool = True
    source_name: str = "Entrada Principal"
    source_entity_id: str = "sensor.seiden_evo_last_person"
    source_photo_attribute: str = "photo_url"
    poll_interval_seconds: int = 3

    @property
    def supervisor_token(self) -> str:
        return os.environ.get("SUPERVISOR_TOKEN", "")


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

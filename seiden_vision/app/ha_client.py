from __future__ import annotations

import logging
from typing import Any

import requests


LOGGER = logging.getLogger(__name__)
BASE_URL = "http://supervisor/core/api"
VERSION = "0.2.0"


class HomeAssistantClient:
    def __init__(self, token: str, timeout: int = 10) -> None:
        self.token = token
        self.timeout = timeout
        self.session = requests.Session()
        if token:
            self.session.headers.update({
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            })

    @property
    def available(self) -> bool:
        return bool(self.token)

    def get_state(self, entity_id: str) -> dict[str, Any] | None:
        if not self.available:
            return None
        try:
            response = self.session.get(
                f"{BASE_URL}/states/{entity_id}", timeout=self.timeout
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            LOGGER.warning("Falha ao ler entidade %s: %s", entity_id, exc)
            return None

    def set_state(
        self,
        entity_id: str,
        state: str | int | float,
        attributes: dict[str, Any] | None = None,
    ) -> bool:
        if not self.available:
            return False
        payload = {"state": str(state), "attributes": attributes or {}}
        try:
            response = self.session.post(
                f"{BASE_URL}/states/{entity_id}",
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            LOGGER.warning("Falha ao publicar %s: %s", entity_id, exc)
            return False

    def publish_operational(
        self,
        *,
        provider: str,
        queue_size: int,
        uptime_seconds: int,
        last_processing_ms: int | None = None,
        region: str | None = None,
    ) -> dict[str, bool]:
        results = {
            "status": self.set_state(
                "sensor.seiden_vision_status",
                "online",
                {
                    "friendly_name": "Seiden Vision - Status",
                    "icon": "mdi:check-network-outline",
                    "version": VERSION,
                    "provider": provider,
                    "region": region,
                },
            ),
            "queue": self.set_state(
                "sensor.seiden_vision_queue",
                queue_size,
                {
                    "friendly_name": "Seiden Vision - Fila",
                    "icon": "mdi:tray-full",
                    "unit_of_measurement": "itens",
                },
            ),
            "provider": self.set_state(
                "sensor.seiden_vision_provider",
                provider,
                {
                    "friendly_name": "Seiden Vision - Provider",
                    "icon": "mdi:brain",
                },
            ),
            "region": self.set_state(
                "sensor.seiden_vision_region",
                region or "local",
                {
                    "friendly_name": "Seiden Vision - Região",
                    "icon": "mdi:map-marker-radius-outline",
                },
            ),
            "version": self.set_state(
                "sensor.seiden_vision_version",
                VERSION,
                {
                    "friendly_name": "Seiden Vision - Versão",
                    "icon": "mdi:tag-outline",
                },
            ),
            "uptime": self.set_state(
                "sensor.seiden_vision_uptime",
                uptime_seconds,
                {
                    "friendly_name": "Seiden Vision - Uptime",
                    "icon": "mdi:timer-outline",
                    "unit_of_measurement": "s",
                    "device_class": "duration",
                },
            ),
        }
        if last_processing_ms is not None:
            results["last_processing"] = self.set_state(
                "sensor.seiden_vision_last_processing",
                last_processing_ms,
                {
                    "friendly_name": "Seiden Vision - Último processamento",
                    "icon": "mdi:speedometer",
                    "unit_of_measurement": "ms",
                },
            )
        return results

    def publish_analysis(self, record: dict[str, Any], stats: dict[str, Any]) -> dict[str, bool]:
        common = {
            "friendly_name": "Seiden Vision - Última análise",
            "icon": "mdi:face-recognition",
            "source": record.get("source"),
            "person": record.get("person"),
            "face_count": record.get("face_count"),
            "confidence": record.get("confidence"),
            "brightness": record.get("brightness"),
            "sharpness": record.get("sharpness"),
            "processing_ms": record.get("processing_ms"),
            "download_ms": record.get("download_ms"),
            "region": (record.get("result") or {}).get("region"),
            "request_id": (record.get("result") or {}).get("request_id"),
            "age_range": (record.get("result") or {}).get("age_range"),
            "gender": (record.get("result") or {}).get("gender"),
            "smile": (record.get("result") or {}).get("smile"),
            "eyes_open": (record.get("result") or {}).get("eyes_open"),
            "face_occluded": (record.get("result") or {}).get("face_occluded"),
            "image_url": record.get("image_url"),
            "analysis_id": record.get("id"),
            "provider": record.get("provider"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
        }
        results = {
            "last_result": self.set_state(
                "sensor.seiden_vision_last_result",
                record.get("dominant_emotion") or record.get("status", "unknown"),
                common,
            ),
            "analyses_today": self.set_state(
                "sensor.seiden_vision_analyses_today",
                stats.get("today", 0),
                {
                    "friendly_name": "Seiden Vision - Análises hoje",
                    "icon": "mdi:counter",
                    **stats,
                },
            ),
        }
        results.update(
            self.publish_operational(
                provider=str(record.get("provider") or "unknown"),
                queue_size=int(record.get("queue_size") or 0),
                uptime_seconds=int(record.get("uptime_seconds") or 0),
                last_processing_ms=record.get("processing_ms"),
                region=(record.get("result") or {}).get("region"),
            )
        )
        return results

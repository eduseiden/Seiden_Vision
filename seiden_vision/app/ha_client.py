from __future__ import annotations

import logging
from typing import Any

import requests


LOGGER = logging.getLogger(__name__)
BASE_URL = "http://supervisor/core/api"
from version import VERSION


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


    def publish_management(self, data: dict[str, Any]) -> dict[str, bool]:
        common = {
            "timezone": data.get("timezone"), "generated_at": data.get("generated_at"),
            "events_yesterday": data.get("events_yesterday"),
            "variation_vs_yesterday_percent": data.get("variation_vs_yesterday_percent"),
            "average_events_7d": data.get("average_events_7d"),
            "variation_vs_7d_percent": data.get("variation_vs_7d_percent"),
            "hourly_today": data.get("hourly_today", []), "daily_trend": data.get("daily_trend", []),
            "sources_today": data.get("sources_today", []), "people_today": data.get("people_today", []),
            "recent_events": data.get("recent_events", []),
        }
        def publish(entity, state, name, icon, **attrs):
            return self.set_state(entity, state, {"friendly_name": name, "icon": icon, **attrs})
        return {
            "health": publish("sensor.seiden_vision_health", data.get("health_status","unknown"), "Seiden Vision - Saúde", "mdi:heart-pulse", success_rate_today=data.get("success_rate_today"), last_success=data.get("last_success"), last_error=data.get("last_error"), error_breakdown_today=data.get("error_breakdown_today",{})),
            "captures_today": publish("sensor.seiden_vision_captures_today", data.get("captures_today",0), "Seiden Vision - Capturas hoje", "mdi:camera-burst"),
            "events_today": publish("sensor.seiden_vision_events_today", data.get("events_today",0), "Seiden Vision - Eventos hoje", "mdi:account-arrow-right-outline", **common),
            "unique_people": publish("sensor.seiden_vision_unique_people_today", data.get("unique_people_today",0), "Seiden Vision - Pessoas distintas hoje", "mdi:account-group-outline", people_today=data.get("people_today",[])),
            "alerts_today": publish("sensor.seiden_vision_alerts_today", data.get("alerts_today",0), "Seiden Vision - Alertas hoje", "mdi:alert-outline", no_face_today=data.get("no_face_today",0), multiple_faces_today=data.get("multiple_faces_today",0), duplicates_today=data.get("duplicates_today",0), errors_today=data.get("errors_today",0)),
            "success_rate": publish("sensor.seiden_vision_success_rate_today", data.get("success_rate_today",100), "Seiden Vision - Taxa de sucesso hoje", "mdi:percent", unit_of_measurement="%"),
            "average_quality": publish("sensor.seiden_vision_average_quality_today", data.get("average_quality_today",0), "Seiden Vision - Qualidade média hoje", "mdi:image-check-outline", unit_of_measurement="%"),
            "average_processing": publish("sensor.seiden_vision_average_processing_today", data.get("average_processing_ms_today",0), "Seiden Vision - Processamento médio hoje", "mdi:speedometer", unit_of_measurement="ms", average_total_ms_today=data.get("average_total_ms_today",0), p50_total_ms_today=data.get("p50_total_ms_today",0), p95_total_ms_today=data.get("p95_total_ms_today",0), average_download_ms_today=data.get("average_download_ms_today",0), average_database_ms_today=data.get("average_database_ms_today",0), average_ha_publish_ms_today=data.get("average_ha_publish_ms_today",0)),
            "p95": publish("sensor.seiden_vision_p95_total_today", data.get("p95_total_ms_today",0), "Seiden Vision - P95 hoje", "mdi:chart-bell-curve", unit_of_measurement="ms"),
            "cost_today": publish("sensor.seiden_vision_estimated_cost_today", data.get("estimated_cost_today_usd",0), "Seiden Vision - Custo estimado hoje", "mdi:currency-usd", unit_of_measurement="USD", aws_calls=data.get("aws_calls_today",0)),
            "cost_week": publish("sensor.seiden_vision_estimated_cost_week", data.get("estimated_cost_week_usd",0), "Seiden Vision - Custo estimado da semana", "mdi:calendar-week", unit_of_measurement="USD", aws_calls=data.get("aws_calls_week",0)),
            "cost_month": publish("sensor.seiden_vision_estimated_cost_month", data.get("estimated_cost_month_usd",0), "Seiden Vision - Custo estimado do mês", "mdi:calendar-month", unit_of_measurement="USD", aws_calls=data.get("aws_calls_month",0)),
            "projected_cost": publish("sensor.seiden_vision_projected_cost_month", data.get("projected_cost_month_usd",0), "Seiden Vision - Projeção mensal", "mdi:trending-up", unit_of_measurement="USD", monthly_budget_usd=data.get("aws_monthly_budget_usd",0), projected_budget_usage_percent=data.get("projected_budget_usage_percent",0), budget_status=data.get("budget_status","ok")),
            "peak_hour": publish("sensor.seiden_vision_peak_hour_today", data.get("peak_hour_today","—"), "Seiden Vision - Horário de pico hoje", "mdi:chart-timeline-variant", first_event_today=data.get("first_event_today"), last_event_today=data.get("last_event_today")),
            "busiest_source": publish("sensor.seiden_vision_busiest_source_today", data.get("busiest_source_today","—"), "Seiden Vision - Fonte mais movimentada hoje", "mdi:door-open", sources_today=data.get("sources_today",[])),
            "no_face": publish("sensor.seiden_vision_no_face_today", data.get("no_face_today",0), "Seiden Vision - Sem face hoje", "mdi:account-off-outline"),
            "multiple_faces": publish("sensor.seiden_vision_multiple_faces_today", data.get("multiple_faces_today",0), "Seiden Vision - Múltiplas faces hoje", "mdi:account-multiple-outline"),
        }

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
            "mouth_open": (record.get("result") or {}).get("mouth_open"),
            "eyeglasses": (record.get("result") or {}).get("eyeglasses"),
            "sunglasses": (record.get("result") or {}).get("sunglasses"),
            "beard": (record.get("result") or {}).get("beard"),
            "mustache": (record.get("result") or {}).get("mustache"),
            "pose": (record.get("result") or {}).get("pose"),
            "emotions": (record.get("result") or {}).get("emotions"),
            "bounding_box": (record.get("result") or {}).get("bounding_box"),
            "operational": (record.get("result") or {}).get("operational"),
            "quality_score": record.get("quality_score"),
            "alert_level": record.get("alert_level"),
            "total_ms": record.get("total_ms"),
            "image_url": record.get("image_url"),
            "analysis_id": record.get("id"),
            "event_id": record.get("event_id"),
            "operational_event": record.get("operational_event"),
            "database_ms": record.get("database_ms"),
            "ha_publish_ms": record.get("ha_publish_ms"),
            "provider": record.get("provider"),
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "source_event_id": record.get("source_event_id"),
            "canonical_event": record.get("canonical_event"),
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
            "quality": self.set_state(
                "sensor.seiden_vision_last_quality",
                record.get("quality_score") or 0,
                {
                    "friendly_name": "Seiden Vision - Qualidade da última imagem",
                    "icon": "mdi:image-check-outline",
                    "unit_of_measurement": "%",
                    "brightness": record.get("brightness"),
                    "sharpness": record.get("sharpness"),
                },
            ),
            "alert": self.set_state(
                "sensor.seiden_vision_last_alert",
                record.get("alert_level") or "ok",
                {
                    "friendly_name": "Seiden Vision - Último alerta",
                    "icon": "mdi:alert-circle-outline",
                    "reasons": ((record.get("result") or {}).get("operational") or {}).get("alert_reasons", []),
                    "analysis_id": record.get("id"),
            "event_id": record.get("event_id"),
            "operational_event": record.get("operational_event"),
            "database_ms": record.get("database_ms"),
            "ha_publish_ms": record.get("ha_publish_ms"),
                },
            ),
            "total_time": self.set_state(
                "sensor.seiden_vision_last_total_time",
                record.get("total_ms") or 0,
                {
                    "friendly_name": "Seiden Vision - Tempo total da última análise",
                    "icon": "mdi:timer-sand-complete",
                    "unit_of_measurement": "ms",
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

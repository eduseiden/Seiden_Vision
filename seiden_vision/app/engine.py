from __future__ import annotations

import hashlib
import logging
import mimetypes
import queue
import threading
import time
import uuid
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import requests

from config import IMAGES_DIR, Settings
from database import Database
from ha_client import HomeAssistantClient
from intelligence import enrich_result
from vision_adapters import create_adapter


LOGGER = logging.getLogger("engine")


@dataclass
class AnalysisJob:
    source: str
    image_url: str
    person: str | None = None
    captured_at: str | None = None


class VisionEngine:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        ha_client: HomeAssistantClient,
    ) -> None:
        self.settings = settings
        self.database = database
        self.ha_client = ha_client
        self.provider = create_adapter(settings)
        self.queue: queue.Queue[AnalysisJob] = queue.Queue(maxsize=500)
        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(
            target=self._worker_loop, name="vision-worker", daemon=True
        )
        self.source_thread = threading.Thread(
            target=self._source_loop, name="source-watcher", daemon=True
        )
        self.operational_thread = threading.Thread(
            target=self._operational_loop, name="operational-publisher", daemon=True
        )
        self.cleanup_thread = threading.Thread(
            target=self._cleanup_loop, name="retention-cleaner", daemon=True
        )
        self.last_source_url: str | None = None
        self.last_processing_ms: int | None = None
        self.started_at = datetime.now(timezone.utc)
        self._started = False
        self._start_lock = threading.Lock()

    def start(self) -> None:
        with self._start_lock:
            if self._started:
                return
            self._started = True
            IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            removed = self.database.purge_older_than(
                self.settings.history_retention_days
            )
            if removed:
                LOGGER.info("Removidos %s registros antigos.", removed)
            self.worker_thread.start()
            self.source_thread.start()
            self.operational_thread.start()
            self.cleanup_thread.start()
            self.database.audit("engine_started", "info", "Seiden Vision 0.3.2 iniciado", {"provider": self.provider.name})
            LOGGER.info(
                "Engine iniciado. Provider=%s, fonte_ha=%s, fila_max=%s",
                self.provider.name,
                self.settings.source_enabled,
                self.queue.maxsize,
            )

    def stop(self) -> None:
        self.stop_event.set()
        LOGGER.info("Sinal de encerramento enviado às threads.")

    def uptime_seconds(self) -> int:
        return int((datetime.now(timezone.utc) - self.started_at).total_seconds())

    def enqueue(self, job: AnalysisJob) -> bool:
        if not job.image_url.lower().startswith(("http://", "https://")):
            raise ValueError("A URL precisa usar HTTP ou HTTPS.")
        try:
            self.queue.put_nowait(job)
            LOGGER.info(
                "Imagem adicionada à fila: %s | fonte=%s | pessoa=%s | fila=%s",
                job.image_url,
                job.source,
                job.person or "não informada",
                self.queue.qsize(),
            )
            return True
        except queue.Full as exc:
            raise RuntimeError("A fila de processamento está cheia.") from exc

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "version": "0.3.2",
            "provider": self.provider.name,
            "region": getattr(self.provider, "region", None),
            "aws_configured": self.settings.aws_configured,
            "aws_analyses_today": self.database.provider_calls_today("aws_rekognition"),
            "aws_daily_limit": self.settings.aws_max_analyses_per_day,
            "aws_estimated_cost_today_usd": round(
                self.database.provider_calls_today("aws_rekognition")
                * self.settings.aws_price_per_1000_images / 1000.0, 4
            ),
            "queue_size": self.queue.qsize(),
            "worker_alive": self.worker_thread.is_alive(),
            "source_watcher_alive": self.source_thread.is_alive(),
            "operational_publisher_alive": self.operational_thread.is_alive(),
            "cleanup_worker_alive": self.cleanup_thread.is_alive(),
            "source_enabled": self.settings.source_enabled,
            "uptime_seconds": self.uptime_seconds(),
            "home_assistant_api": self.ha_client.available,
            "last_processing_ms": self.last_processing_ms,
        }

    def _download(self, url: str) -> tuple[bytes, str, int]:
        started = time.perf_counter()
        max_bytes = self.settings.maximum_image_size_mb * 1024 * 1024
        with requests.get(
            url,
            timeout=self.settings.download_timeout_seconds,
            stream=True,
            headers={"User-Agent": "Seiden-Vision/0.3.2"},
        ) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";")[0].lower()
            if content_type and not content_type.startswith("image/"):
                raise ValueError(f"Conteúdo recebido não é imagem: {content_type}")
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > max_bytes:
                raise ValueError("Imagem excede o tamanho máximo configurado.")

            chunks: list[bytes] = []
            total = 0
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError("Imagem excede o tamanho máximo configurado.")
                chunks.append(chunk)

        data = b"".join(chunks)
        if not data:
            raise ValueError("A imagem recebida está vazia.")
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return data, content_type, elapsed_ms

    def _retain(self, image_bytes: bytes, image_hash: str, content_type: str) -> str:
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        path = IMAGES_DIR / (
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image_hash[:12]}{extension}"
        )
        path.write_bytes(image_bytes)
        return str(path)

    @staticmethod
    def _ok_label(value: bool) -> str:
        return "OK" if value else "FALHA"

    def _process(self, job: AnalysisJob) -> None:
        overall_started = time.perf_counter()
        created_at = datetime.now(timezone.utc).isoformat()
        event_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{uuid.uuid4().hex[:10]}"
        base: dict[str, Any] = {
            "event_id": event_id,
            "created_at": created_at,
            "captured_at": job.captured_at,
            "source": job.source,
            "person": job.person,
            "image_url": job.image_url,
            "provider": self.provider.name,
            "operational_event": 1,
        }
        LOGGER.info("──────────── Nova análise ────────────")
        LOGGER.info("Fonte............. %s", job.source)
        LOGGER.info("Pessoa............ %s", job.person or "não informada")
        LOGGER.info("URL................ %s", job.image_url)

        try:
            image_bytes, content_type, download_ms = self._download(job.image_url)
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            base["image_hash"] = image_hash

            LOGGER.info(
                "Download........... %.1f KB (%s ms)",
                len(image_bytes) / 1024,
                download_ms,
            )
            LOGGER.info("SHA256............. %s", image_hash[:16])

            duplicate = self.database.find_recent_duplicate(
                image_hash, self.settings.duplicate_window_minutes
            )
            if duplicate:
                base.update({
                    "status": "duplicate",
                    "operational_event": 0,
                    "face_count": duplicate.get("face_count", 0),
                    "dominant_emotion": duplicate.get("dominant_emotion"),
                    "confidence": duplicate.get("confidence"),
                    "brightness": duplicate.get("brightness"),
                    "sharpness": duplicate.get("sharpness"),
                    "processing_ms": 0,
                    "duplicate_of": duplicate.get("id"),
                    "result": {"duplicate": True, "duplicate_of": duplicate.get("id")},
                })
                record_id = self.database.insert(base)
                LOGGER.info("Duplicidade......... SIM (registro %s)", duplicate.get("id"))
                LOGGER.info("SQLite.............. OK (registro %s)", record_id)
                return

            LOGGER.info("Duplicidade......... NÃO")
            if self.provider.name == "aws_rekognition":
                used_today = self.database.provider_calls_today(self.provider.name)
                if used_today >= self.settings.aws_max_analyses_per_day:
                    raise RuntimeError(
                        f"Limite diário do AWS Rekognition atingido: {used_today}/"
                        f"{self.settings.aws_max_analyses_per_day}."
                    )
                LOGGER.info(
                    "Cota AWS............ %s/%s análises concluídas hoje",
                    used_today,
                    self.settings.aws_max_analyses_per_day,
                )
            result = self.provider.analyze(
                image_bytes, self.settings.minimum_confidence
            )
            result = enrich_result(
                result,
                min_brightness=self.settings.quality_min_brightness,
                min_sharpness=self.settings.quality_min_sharpness,
            )
            if self.provider.name == "aws_rekognition":
                self.database.record_provider_call(self.provider.name, "analyze")
            retained_path = None
            if self.settings.retain_images:
                retained_path = self._retain(image_bytes, image_hash, content_type)

            operational_event = self.database.is_operational_event(job.person, job.source, self.settings.person_event_cooldown_seconds)
            total_ms = int((time.perf_counter() - overall_started) * 1000)
            operational = result.get("operational", {})
            base.update({
                "status": "success",
                "operational_event": 1 if operational_event else 0,
                "face_count": result.get("face_count", 0),
                "dominant_emotion": result.get("dominant_emotion"),
                "confidence": result.get("confidence"),
                "brightness": result.get("quality", {}).get("brightness"),
                "sharpness": result.get("quality", {}).get("sharpness"),
                "processing_ms": result.get("processing_ms"),
                "download_ms": download_ms,
                "total_ms": total_ms,
                "quality_score": operational.get("quality_score"),
                "alert_level": operational.get("alert_level"),
                "duplicate_of": None,
                "retained_path": retained_path,
                "result": result,
                "error": None,
            })
            db_started = time.perf_counter()
            record_id = self.database.insert(base)
            database_ms = int((time.perf_counter() - db_started) * 1000)
            base["database_ms"] = database_ms
            base["id"] = record_id
            base["queue_size"] = self.queue.qsize()
            base["uptime_seconds"] = self.uptime_seconds()
            self.last_processing_ms = int(base.get("processing_ms") or 0)

            LOGGER.info("Provider............ %s", self.provider.name)
            if result.get("region"):
                LOGGER.info("Região AWS.......... %s", result.get("region"))
            if result.get("request_id"):
                LOGGER.info("AWS Request ID...... %s", result.get("request_id"))
            LOGGER.info("Faces............... %s", base.get("face_count"))
            LOGGER.info("Resultado........... %s", base.get("dominant_emotion"))
            LOGGER.info("Confiança........... %.2f%%", base.get("confidence") or 0)
            LOGGER.info("Brightness.......... %s", base.get("brightness"))
            LOGGER.info("Sharpness........... %s", base.get("sharpness"))
            LOGGER.info("Qualidade........... %s/100", operational.get("quality_score"))
            LOGGER.info("Alerta.............. %s", operational.get("alert_level", "ok").upper())
            if operational.get("alert_reasons"):
                LOGGER.info("Motivos............. %s", " | ".join(operational.get("alert_reasons", [])))
            emotions = result.get("emotions") or {}
            if emotions:
                top = sorted(emotions.items(), key=lambda item: item[1], reverse=True)[:5]
                LOGGER.info("Emoções............. %s", " | ".join(f"{k}={v:.2f}%" for k, v in top))
            LOGGER.info("Processamento....... %s ms", base.get("processing_ms"))
            LOGGER.info("Download imagem..... %s ms", download_ms)
            LOGGER.info("SQLite.............. OK (registro %s)", record_id)

            if self.settings.publish_to_home_assistant:
                ha_started = time.perf_counter()
                publish_results = self.ha_client.publish_analysis(
                    base, self.database.stats()
                )
                management = self.database.management_stats(
                    self.settings.management_timezone,
                    self.settings.management_trend_days,
                    self.settings.aws_price_per_1000_images,
                    self.settings.aws_monthly_budget_usd,
                )
                publish_results.update(self.ha_client.publish_management(management))
                ha_publish_ms = int((time.perf_counter() - ha_started) * 1000)
                final_total_ms = int((time.perf_counter() - overall_started) * 1000)
                self.database.update_timings(record_id, database_ms=database_ms, ha_publish_ms=ha_publish_ms, total_ms=final_total_ms)
                base["ha_publish_ms"] = ha_publish_ms
                base["total_ms"] = final_total_ms
                LOGGER.info(
                    "HA Publish.......... %s",
                    "OK" if all(publish_results.values()) else "PARCIAL/FALHA",
                )
            else:
                LOGGER.info("HA Publish.......... DESATIVADO")

            LOGGER.info("Tempo total......... %s ms", total_ms)
            LOGGER.info("──────── Análise %s concluída ────────", record_id)

        except Exception as exc:
            LOGGER.exception("Falha ao processar imagem: %s", exc)
            category = self._classify_error(exc)
            error_record = {
                **base,
                "image_hash": base.get("image_hash", ""),
                "status": "error",
                "error_category": category,
                "operational_event": 0,
                "face_count": 0,
                "result": {},
                "error": str(exc),
            }
            record_id = self.database.insert(error_record)
            LOGGER.error("SQLite.............. erro registrado como %s", record_id)
            self.database.audit("analysis_error", "error", str(exc), {"event_id": base.get("event_id"), "category": category, "source": job.source})

    @staticmethod
    def _classify_error(exc: Exception) -> str:
        text = str(exc).lower()
        if isinstance(exc, requests.RequestException) or "download" in text or "http" in text:
            return "download_error"
        if "aws" in text or "rekognition" in text or "credential" in text or "token" in text:
            return "provider_error"
        if "sqlite" in text or "database" in text:
            return "database_error"
        return "processing_error"

    def _cleanup_images(self) -> dict[str, int]:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        files = sorted((p for p in IMAGES_DIR.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime)
        cutoff = time.time() - self.settings.image_retention_days * 86400
        removed = 0
        for path in list(files):
            if path.stat().st_mtime < cutoff:
                try:
                    path.unlink(); removed += 1; files.remove(path)
                except OSError:
                    LOGGER.warning("Não foi possível remover imagem antiga: %s", path)
        excess = max(0, len(files) - self.settings.max_stored_images)
        for path in files[:excess]:
            try:
                path.unlink(); removed += 1
            except OSError:
                LOGGER.warning("Não foi possível remover imagem excedente: %s", path)
        if removed:
            self.database.audit("image_cleanup", "info", f"{removed} imagens removidas", {"retention_days": self.settings.image_retention_days, "max_images": self.settings.max_stored_images})
        return {"removed": removed, "remaining": max(0, len(files) - excess)}

    def _cleanup_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                self._cleanup_images()
            except Exception as exc:
                LOGGER.exception("Falha na limpeza de imagens: %s", exc)
                self.database.audit("cleanup_error", "warning", str(exc))
            self.stop_event.wait(self.settings.cleanup_interval_hours * 3600)

    def test_provider(self, image_url: str | None = None) -> dict[str, Any]:
        resolved_url = image_url
        if not resolved_url and self.settings.source_enabled and self.ha_client.available:
            state = self.ha_client.get_state(self.settings.source_entity_id)
            if state:
                resolved_url = state.get("attributes", {}).get(
                    self.settings.source_photo_attribute
                )
        if not resolved_url:
            raise ValueError(
                "Nenhuma URL foi informada e a fonte configurada não possui foto disponível."
            )
        image_bytes, content_type, download_ms = self._download(str(resolved_url))
        if self.provider.name == "aws_rekognition":
            used_today = self.database.provider_calls_today(self.provider.name)
            if used_today >= self.settings.aws_max_analyses_per_day:
                raise RuntimeError("Limite diário do AWS Rekognition atingido.")
        result = self.provider.analyze(image_bytes, self.settings.minimum_confidence)
        result = enrich_result(
            result,
            min_brightness=self.settings.quality_min_brightness,
            min_sharpness=self.settings.quality_min_sharpness,
        )
        if self.provider.name == "aws_rekognition":
            self.database.record_provider_call(self.provider.name, "test")
        return {
            "status": "ok",
            "provider": self.provider.name,
            "region": getattr(self.provider, "region", None),
            "image_url": str(resolved_url),
            "content_type": content_type,
            "image_size_bytes": len(image_bytes),
            "download_ms": download_ms,
            "processing_ms": result.get("processing_ms"),
            "face_count": result.get("face_count"),
            "dominant_emotion": result.get("dominant_emotion"),
            "confidence": result.get("confidence"),
            "request_id": result.get("request_id"),
        }

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.queue.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self._process(job)
            finally:
                self.queue.task_done()

    def _source_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.settings.source_enabled and self.ha_client.available:
                state = self.ha_client.get_state(self.settings.source_entity_id)
                if state:
                    attributes = state.get("attributes", {})
                    image_url = attributes.get(self.settings.source_photo_attribute)
                    person = state.get("state")
                    if image_url and image_url != self.last_source_url:
                        self.last_source_url = str(image_url)
                        try:
                            self.enqueue(
                                AnalysisJob(
                                    source=self.settings.source_name,
                                    image_url=str(image_url),
                                    person=None
                                    if person in ("unknown", "unavailable")
                                    else str(person),
                                )
                            )
                        except Exception as exc:
                            LOGGER.warning(
                                "Não foi possível enfileirar a fonte: %s", exc
                            )
            self.stop_event.wait(self.settings.poll_interval_seconds)

    def _operational_loop(self) -> None:
        while not self.stop_event.is_set():
            if self.settings.publish_to_home_assistant and self.ha_client.available:
                results = self.ha_client.publish_operational(
                    provider=self.provider.name,
                    queue_size=self.queue.qsize(),
                    uptime_seconds=self.uptime_seconds(),
                    last_processing_ms=self.last_processing_ms,
                    region=getattr(self.provider, "region", None),
                )
                management = self.database.management_stats(
                    self.settings.management_timezone,
                    self.settings.management_trend_days,
                    self.settings.aws_price_per_1000_images,
                    self.settings.aws_monthly_budget_usd,
                )
                results.update(self.ha_client.publish_management(management))
                if not all(results.values()):
                    LOGGER.debug("Publicação operacional/gerencial parcial: %s", results)
            self.stop_event.wait(30)

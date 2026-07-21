from __future__ import annotations

import hashlib
import logging
import mimetypes
import queue
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from config import IMAGES_DIR, Settings
from database import Database
from ha_client import HomeAssistantClient
from providers import create_provider


LOGGER = logging.getLogger(__name__)


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
        self.provider = create_provider(settings.provider)
        self.queue: queue.Queue[AnalysisJob] = queue.Queue(maxsize=500)
        self.stop_event = threading.Event()
        self.worker_thread = threading.Thread(
            target=self._worker_loop, name="vision-worker", daemon=True
        )
        self.source_thread = threading.Thread(
            target=self._source_loop, name="source-watcher", daemon=True
        )
        self.last_source_url: str | None = None
        self.started_at = datetime.now(timezone.utc)

    def start(self) -> None:
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        removed = self.database.purge_older_than(self.settings.history_retention_days)
        if removed:
            LOGGER.info("Removidos %s registros antigos.", removed)
        self.worker_thread.start()
        self.source_thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def enqueue(self, job: AnalysisJob) -> bool:
        if not job.image_url.lower().startswith(("http://", "https://")):
            raise ValueError("A URL precisa usar HTTP ou HTTPS.")
        try:
            self.queue.put_nowait(job)
            LOGGER.info("Imagem adicionada à fila: %s", job.image_url)
            return True
        except queue.Full as exc:
            raise RuntimeError("A fila de processamento está cheia.") from exc

    def health(self) -> dict[str, Any]:
        uptime = int((datetime.now(timezone.utc) - self.started_at).total_seconds())
        return {
            "status": "ok",
            "version": "0.1.0",
            "provider": self.provider.name,
            "queue_size": self.queue.qsize(),
            "worker_alive": self.worker_thread.is_alive(),
            "source_watcher_alive": self.source_thread.is_alive(),
            "source_enabled": self.settings.source_enabled,
            "uptime_seconds": uptime,
            "home_assistant_api": self.ha_client.available,
        }

    def _download(self, url: str) -> tuple[bytes, str]:
        max_bytes = self.settings.maximum_image_size_mb * 1024 * 1024
        with requests.get(
            url,
            timeout=self.settings.download_timeout_seconds,
            stream=True,
            headers={"User-Agent": "Seiden-Vision/0.1.0"},
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
        return data, content_type

    def _retain(self, image_bytes: bytes, image_hash: str, content_type: str) -> str:
        extension = mimetypes.guess_extension(content_type) or ".jpg"
        path = IMAGES_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{image_hash[:12]}{extension}"
        path.write_bytes(image_bytes)
        return str(path)

    def _process(self, job: AnalysisJob) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        base: dict[str, Any] = {
            "created_at": created_at,
            "captured_at": job.captured_at,
            "source": job.source,
            "person": job.person,
            "image_url": job.image_url,
            "provider": self.provider.name,
        }
        try:
            image_bytes, content_type = self._download(job.image_url)
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            base["image_hash"] = image_hash

            duplicate = self.database.find_recent_duplicate(
                image_hash, self.settings.duplicate_window_minutes
            )
            if duplicate:
                base.update({
                    "status": "duplicate",
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
                LOGGER.info("Imagem duplicada ignorada. Registro %s.", record_id)
                return

            result = self.provider.analyze(
                image_bytes, self.settings.minimum_confidence
            )
            retained_path = None
            if self.settings.retain_images:
                retained_path = self._retain(image_bytes, image_hash, content_type)

            base.update({
                "status": "success",
                "face_count": result.get("face_count", 0),
                "dominant_emotion": result.get("dominant_emotion"),
                "confidence": result.get("confidence"),
                "brightness": result.get("quality", {}).get("brightness"),
                "sharpness": result.get("quality", {}).get("sharpness"),
                "processing_ms": result.get("processing_ms"),
                "duplicate_of": None,
                "retained_path": retained_path,
                "result": result,
                "error": None,
            })
            record_id = self.database.insert(base)
            base["id"] = record_id
            LOGGER.info(
                "Análise %s concluída: %s (%.2f%%).",
                record_id,
                base.get("dominant_emotion"),
                base.get("confidence") or 0,
            )
            if self.settings.publish_to_home_assistant:
                self.ha_client.publish_analysis(base, self.database.stats())

        except Exception as exc:
            LOGGER.exception("Falha ao processar imagem: %s", exc)
            error_record = {
                **base,
                "image_hash": base.get("image_hash", ""),
                "status": "error",
                "face_count": 0,
                "result": {},
                "error": str(exc),
            }
            self.database.insert(error_record)

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
                        self.last_source_url = image_url
                        try:
                            self.enqueue(
                                AnalysisJob(
                                    source=self.settings.source_name,
                                    image_url=str(image_url),
                                    person=None if person in ("unknown", "unavailable") else str(person),
                                )
                            )
                        except Exception as exc:
                            LOGGER.warning("Não foi possível enfileirar a fonte: %s", exc)
            self.stop_event.wait(self.settings.poll_interval_seconds)

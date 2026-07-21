from __future__ import annotations

import logging
import signal
import sys
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request

from config import DB_PATH, load_settings
from database import Database
from engine import AnalysisJob, VisionEngine
from ha_client import HomeAssistantClient


settings = load_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)-8s] %(name)s: %(message)s",
)
LOGGER = logging.getLogger("seiden_vision")

database = Database(DB_PATH)
ha_client = HomeAssistantClient(
    token=settings.supervisor_token,
    timeout=settings.download_timeout_seconds,
)
engine = VisionEngine(settings, database, ha_client)

app = Flask(__name__)


@app.after_request
def add_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/")
def index():
    return render_template(
        "index.html",
        version="0.1.0",
        provider=settings.provider,
        source_enabled=settings.source_enabled,
        source_name=settings.source_name,
    )


@app.get("/api/v1/health")
def health():
    return jsonify(engine.health())


@app.get("/api/v1/stats")
def stats():
    return jsonify(database.stats())


@app.get("/api/v1/analyses")
def analyses():
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    return jsonify({"items": database.list_analyses(limit)})


@app.post("/api/v1/analyze")
def analyze():
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    image_url = str(payload.get("image_url", "")).strip()
    source = str(payload.get("source", "Manual")).strip() or "Manual"
    person = payload.get("person")
    captured_at = payload.get("captured_at")

    if not image_url:
        return jsonify({"status": "error", "message": "image_url é obrigatório."}), 400

    try:
        engine.enqueue(
            AnalysisJob(
                source=source,
                image_url=image_url,
                person=str(person) if person is not None else None,
                captured_at=str(captured_at) if captured_at is not None else None,
            )
        )
    except (ValueError, RuntimeError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({
        "status": "queued",
        "queue_size": engine.queue.qsize(),
        "received_at": datetime.now(timezone.utc).isoformat(),
    }), 202


@app.delete("/api/v1/analyses")
def clear_analyses():
    count = database.clear()
    return jsonify({"status": "ok", "deleted": count})


@app.post("/api/v1/publish-test")
def publish_test():
    ok = ha_client.set_state(
        "sensor.seiden_vision_status",
        "online",
        {
            "friendly_name": "Seiden Vision - Status",
            "icon": "mdi:check-network-outline",
            "version": "0.1.0",
            "provider": settings.provider,
            "test": True,
        },
    )
    if not ok:
        return jsonify({"status": "error", "message": "Home Assistant API indisponível."}), 503
    return jsonify({"status": "ok"})


def shutdown_handler(signum, frame):
    LOGGER.info("Encerrando Seiden Vision...")
    engine.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    engine.start()
    LOGGER.info(
        "Seiden Vision 0.1.0 iniciado. Provider=%s, source=%s",
        settings.provider,
        settings.source_enabled,
    )
    app.run(host="0.0.0.0", port=8099, threaded=True, use_reloader=False)

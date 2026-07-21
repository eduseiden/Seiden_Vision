from __future__ import annotations

import atexit
import logging
from datetime import datetime, timezone
from typing import Any

from flask import Flask, jsonify, render_template, request

from config import DB_PATH, load_settings
from database import Database
from engine import AnalysisJob, VisionEngine
from ha_client import HomeAssistantClient


VERSION = "0.1.1"
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
engine.start()
atexit.register(engine.stop)


@app.after_request
def add_headers(response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.get("/")
def index():
    return render_template(
        "index.html",
        version=VERSION,
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
    results = ha_client.publish_operational(
        provider=settings.provider,
        queue_size=engine.queue.qsize(),
        uptime_seconds=engine.uptime_seconds(),
        last_processing_ms=engine.last_processing_ms,
    )
    if not results or not all(results.values()):
        return jsonify({
            "status": "error",
            "message": "Publicação parcial ou Home Assistant API indisponível.",
            "results": results,
        }), 503
    return jsonify({"status": "ok", "results": results})


LOGGER.info(
    "Seiden Vision %s carregado. Provider=%s, source=%s",
    VERSION,
    settings.provider,
    settings.source_enabled,
)

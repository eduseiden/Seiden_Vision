from __future__ import annotations

import atexit
import csv
import io
import logging
from datetime import datetime, timezone
from typing import Any

from flask import Flask, Response, jsonify, render_template, request

from config import DB_PATH, load_settings
from database import Database
from engine import AnalysisJob, VisionEngine
from ha_client import HomeAssistantClient


VERSION = "0.3.2"
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
    data = database.stats()
    calls = database.provider_calls_today("aws_rekognition")
    data.update({
        "aws_calls_today": calls,
        "aws_daily_limit": settings.aws_max_analyses_per_day,
        "aws_quota_percent": round(calls * 100 / settings.aws_max_analyses_per_day, 2),
        "aws_estimated_cost_today_usd": round(calls * settings.aws_price_per_1000_images / 1000.0, 4),
    })
    return jsonify(data)


@app.get("/api/v1/analyses")
def analyses():
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    return jsonify({"items": database.list_analyses(limit)})


@app.get("/api/v1/management/summary")
def management_summary():
    return jsonify(database.management_stats(
        settings.management_timezone,
        settings.management_trend_days,
        settings.aws_price_per_1000_images,
        settings.aws_monthly_budget_usd,
    ))


@app.get("/api/v1/management/daily")
def management_daily():
    data = database.management_stats(settings.management_timezone, settings.management_trend_days, settings.aws_price_per_1000_images, settings.aws_monthly_budget_usd)
    return jsonify({"timezone": data["timezone"], "items": data["daily_trend"]})


@app.get("/api/v1/management/hourly")
def management_hourly():
    data = database.management_stats(settings.management_timezone, settings.management_trend_days, settings.aws_price_per_1000_images, settings.aws_monthly_budget_usd)
    return jsonify({"timezone": data["timezone"], "items": data["hourly_today"]})


@app.get("/api/v1/management/people")
def management_people():
    data = database.management_stats(settings.management_timezone, settings.management_trend_days, settings.aws_price_per_1000_images, settings.aws_monthly_budget_usd)
    return jsonify({"timezone": data["timezone"], "items": data["people_today"]})


@app.get("/api/v1/management/sources")
def management_sources():
    data = database.management_stats(settings.management_timezone, settings.management_trend_days, settings.aws_price_per_1000_images, settings.aws_monthly_budget_usd)
    return jsonify({"timezone": data["timezone"], "items": data["sources_today"]})


@app.get("/api/v1/audit")
def audit_log():
    try:
        limit = int(request.args.get("limit", "50"))
    except ValueError:
        limit = 50
    return jsonify({"items": database.list_audit(limit)})


@app.get("/api/v1/export/events.csv")
def export_events_csv():
    try:
        limit = int(request.args.get("limit", "5000"))
    except ValueError:
        limit = 5000
    items = database.list_analyses(min(limit, 5000))
    output = io.StringIO()
    fields = ["event_id", "created_at", "captured_at", "source", "person", "status", "error_category", "operational_event", "face_count", "dominant_emotion", "confidence", "brightness", "sharpness", "quality_score", "alert_level", "download_ms", "processing_ms", "database_ms", "ha_publish_ms", "total_ms", "image_url", "retained_path", "error"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for item in reversed(items):
        writer.writerow(item)
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=seiden_vision_events.csv"})


@app.get("/api/v1/export/daily.csv")
def export_daily_csv():
    data = database.management_stats(settings.management_timezone, settings.management_trend_days, settings.aws_price_per_1000_images, settings.aws_monthly_budget_usd)
    output = io.StringIO()
    fields = ["date", "captures", "events", "unique_people", "alerts", "average_quality", "average_total_ms"]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(data.get("daily_trend", []))
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=seiden_vision_daily.csv"})


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


@app.post("/api/v1/provider/test")
def provider_test():
    payload: dict[str, Any] = request.get_json(silent=True) or {}
    image_url = str(payload.get("image_url", "")).strip() or None
    try:
        return jsonify(engine.test_provider(image_url))
    except (ValueError, RuntimeError) as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        LOGGER.exception("Falha no teste do adaptador: %s", exc)
        return jsonify({"status": "error", "message": str(exc)}), 502


@app.post("/api/v1/publish-test")
def publish_test():
    results = ha_client.publish_operational(
        provider=settings.provider,
        queue_size=engine.queue.qsize(),
        uptime_seconds=engine.uptime_seconds(),
        last_processing_ms=engine.last_processing_ms,
        region=getattr(engine.provider, "region", None),
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

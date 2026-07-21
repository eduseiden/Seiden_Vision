from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pathlib import Path
from typing import Any


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    captured_at TEXT,
                    source TEXT NOT NULL,
                    person TEXT,
                    image_url TEXT NOT NULL,
                    image_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    face_count INTEGER NOT NULL DEFAULT 0,
                    dominant_emotion TEXT,
                    confidence REAL,
                    brightness REAL,
                    sharpness REAL,
                    processing_ms INTEGER,
                    download_ms INTEGER,
                    total_ms INTEGER,
                    quality_score REAL,
                    alert_level TEXT,
                    duplicate_of INTEGER,
                    retained_path TEXT,
                    result_json TEXT NOT NULL,
                    error TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analyses_hash_created "
                "ON analyses(image_hash, created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_analyses_created "
                "ON analyses(created_at)"
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS provider_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    operation TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_provider_usage_created "
                "ON provider_usage(provider, created_at)"
            )
            existing = {row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
            for column, definition in {
                "download_ms": "INTEGER",
                "total_ms": "INTEGER",
                "quality_score": "REAL",
                "alert_level": "TEXT",
            }.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE analyses ADD COLUMN {column} {definition}")

    def find_recent_duplicate(self, image_hash: str, minutes: int) -> dict[str, Any] | None:
        if minutes <= 0:
            return None
        threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM analyses
                WHERE image_hash = ?
                  AND created_at >= ?
                  AND status = 'success'
                ORDER BY id DESC
                LIMIT 1
                """,
                (image_hash, threshold.isoformat()),
            ).fetchone()
        return dict(row) if row else None

    def insert(self, record: dict[str, Any]) -> int:
        payload = dict(record)
        payload["result_json"] = json.dumps(
            payload.get("result", {}), ensure_ascii=False, separators=(",", ":")
        )
        columns = [
            "created_at", "captured_at", "source", "person", "image_url",
            "image_hash", "provider", "status", "face_count",
            "dominant_emotion", "confidence", "brightness", "sharpness",
            "processing_ms", "download_ms", "total_ms", "quality_score", "alert_level",
            "duplicate_of", "retained_path", "result_json", "error",
        ]
        values = [payload.get(column) for column in columns]
        placeholders = ",".join("?" for _ in columns)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                f"INSERT INTO analyses ({','.join(columns)}) VALUES ({placeholders})",
                values,
            )
            return int(cursor.lastrowid)

    def list_analyses(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM analyses ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["result"] = json.loads(item.pop("result_json"))
            except (json.JSONDecodeError, TypeError):
                item["result"] = {}
            result.append(item)
        return result

    def stats(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
            today_count = conn.execute(
                "SELECT COUNT(*) FROM analyses WHERE substr(created_at,1,10)=?",
                (today,),
            ).fetchone()[0]
            successful = conn.execute(
                "SELECT COUNT(*) FROM analyses WHERE status='success'"
            ).fetchone()[0]
            duplicates = conn.execute(
                "SELECT COUNT(*) FROM analyses WHERE status='duplicate'"
            ).fetchone()[0]
            errors = conn.execute(
                "SELECT COUNT(*) FROM analyses WHERE status='error'"
            ).fetchone()[0]
            avg_ms = conn.execute(
                "SELECT AVG(processing_ms) FROM analyses WHERE status='success'"
            ).fetchone()[0]
            avg_total_ms = conn.execute(
                "SELECT AVG(total_ms) FROM analyses WHERE status='success'"
            ).fetchone()[0]
            alerts = conn.execute(
                "SELECT COUNT(*) FROM analyses WHERE alert_level IN ('warning','critical')"
            ).fetchone()[0]
            avg_quality = conn.execute(
                "SELECT AVG(quality_score) FROM analyses WHERE status='success'"
            ).fetchone()[0]
        return {
            "total": total,
            "today": today_count,
            "successful": successful,
            "duplicates": duplicates,
            "errors": errors,
            "average_processing_ms": round(avg_ms or 0, 1),
            "average_total_ms": round(avg_total_ms or 0, 1),
            "alerts": alerts,
            "average_quality_score": round(avg_quality or 0, 1),
        }

    def record_provider_call(self, provider: str, operation: str = "analyze") -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO provider_usage (created_at, provider, operation) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), provider, operation),
            )
            return int(cursor.lastrowid)

    def provider_calls_today(self, provider: str) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connect() as conn:
            return int(conn.execute(
                "SELECT COUNT(*) FROM provider_usage WHERE substr(created_at,1,10)=? AND provider=?",
                (today, provider),
            ).fetchone()[0])


    @staticmethod
    def _safe_timezone(name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    def _management_rows(self, days: int = 32) -> list[dict[str, Any]]:
        threshold = datetime.now(timezone.utc) - timedelta(days=max(2, days))
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, created_at, captured_at, source, person, status, face_count,
                       quality_score, alert_level, processing_ms, total_ms, image_url,
                       retained_path, dominant_emotion
                FROM analyses
                WHERE created_at >= ?
                ORDER BY created_at ASC
                """,
                (threshold.isoformat(),),
            ).fetchall()
        return [dict(row) for row in rows]

    def management_stats(
        self,
        timezone_name: str = "America/Sao_Paulo",
        trend_days: int = 14,
        aws_price_per_1000_images: float = 1.0,
    ) -> dict[str, Any]:
        tz = self._safe_timezone(timezone_name)
        now_local = datetime.now(timezone.utc).astimezone(tz)
        today = now_local.date()
        yesterday = today - timedelta(days=1)
        trend_days = max(7, min(int(trend_days), 90))
        rows = self._management_rows(max(trend_days + 8, 32))

        def local_dt(row: dict[str, Any]) -> datetime:
            raw = row.get("captured_at") or row.get("created_at")
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except (TypeError, ValueError):
                dt = datetime.now(timezone.utc)
            return dt.astimezone(tz)

        normalized = [(row, local_dt(row)) for row in rows]
        successes = [(r, dt) for r, dt in normalized if r.get("status") == "success"]
        today_rows = [(r, dt) for r, dt in successes if dt.date() == today]
        yesterday_rows = [(r, dt) for r, dt in successes if dt.date() == yesterday]

        def distinct_people(items):
            return sorted({str(r.get("person")).strip() for r, _ in items if r.get("person") and str(r.get("person")).strip().lower() not in {"unknown", "unavailable", "none"}})

        def avg(items, field):
            vals = [float(r[field]) for r, _ in items if r.get(field) is not None]
            return round(sum(vals) / len(vals), 1) if vals else 0.0

        def count_alerts(items):
            return sum(1 for r, _ in items if r.get("alert_level") in ("warning", "critical"))

        today_count = len(today_rows)
        yesterday_count = len(yesterday_rows)
        variation = round((today_count - yesterday_count) * 100 / yesterday_count, 1) if yesterday_count else (100.0 if today_count else 0.0)

        daily = []
        historical_counts = []
        for offset in range(trend_days - 1, -1, -1):
            day = today - timedelta(days=offset)
            items = [(r, dt) for r, dt in successes if dt.date() == day]
            count = len(items)
            if day < today:
                historical_counts.append(count)
            daily.append({
                "date": day.isoformat(),
                "events": count,
                "unique_people": len(distinct_people(items)),
                "alerts": count_alerts(items),
                "average_quality": avg(items, "quality_score"),
                "average_total_ms": avg(items, "total_ms"),
            })
        average_7d = round(sum(historical_counts[-7:]) / len(historical_counts[-7:]), 1) if historical_counts[-7:] else 0.0
        versus_7d = round((today_count - average_7d) * 100 / average_7d, 1) if average_7d else (100.0 if today_count else 0.0)

        hourly = []
        hour_counts = {hour: 0 for hour in range(24)}
        for _, dt in today_rows:
            hour_counts[dt.hour] += 1
        for hour in range(24):
            hourly.append({"hour": f"{hour:02d}:00", "events": hour_counts[hour]})
        peak_hour_num = max(hour_counts, key=hour_counts.get) if today_count else None
        peak_hour = f"{peak_hour_num:02d}:00" if peak_hour_num is not None else "—"

        source_counts: dict[str, int] = {}
        person_counts: dict[str, int] = {}
        for row, _ in today_rows:
            source = str(row.get("source") or "Não informada")
            source_counts[source] = source_counts.get(source, 0) + 1
            person = str(row.get("person") or "Não identificada")
            person_counts[person] = person_counts.get(person, 0) + 1
        sources = [{"source": k, "events": v} for k, v in sorted(source_counts.items(), key=lambda x: (-x[1], x[0]))]
        people = [{"person": k, "events": v} for k, v in sorted(person_counts.items(), key=lambda x: (-x[1], x[0]))]
        busiest_source = sources[0]["source"] if sources else "—"

        first_event = min((dt for _, dt in today_rows), default=None)
        last_event = max((dt for _, dt in today_rows), default=None)
        duplicate_today = sum(1 for r, dt in normalized if dt.date() == today and r.get("status") == "duplicate")
        errors_today = sum(1 for r, dt in normalized if dt.date() == today and r.get("status") == "error")
        no_face_today = sum(1 for r, _ in today_rows if int(r.get("face_count") or 0) == 0)
        multiple_faces_today = sum(1 for r, _ in today_rows if int(r.get("face_count") or 0) > 1)
        alerts_today = count_alerts(today_rows)

        recent = []
        for row, dt in sorted(today_rows, key=lambda item: item[1], reverse=True)[:20]:
            recent.append({
                "id": row.get("id"), "time": dt.isoformat(), "person": row.get("person"),
                "source": row.get("source"), "quality_score": row.get("quality_score"),
                "alert_level": row.get("alert_level"), "image_url": row.get("image_url"),
                "emotion": row.get("dominant_emotion"),
            })

        return {
            "timezone": timezone_name,
            "generated_at": now_local.isoformat(),
            "events_today": today_count,
            "events_yesterday": yesterday_count,
            "variation_vs_yesterday_percent": variation,
            "average_events_7d": average_7d,
            "variation_vs_7d_percent": versus_7d,
            "unique_people_today": len(distinct_people(today_rows)),
            "people_today": people,
            "alerts_today": alerts_today,
            "no_face_today": no_face_today,
            "multiple_faces_today": multiple_faces_today,
            "duplicates_today": duplicate_today,
            "errors_today": errors_today,
            "average_quality_today": avg(today_rows, "quality_score"),
            "average_processing_ms_today": avg(today_rows, "processing_ms"),
            "average_total_ms_today": avg(today_rows, "total_ms"),
            "first_event_today": first_event.isoformat() if first_event else None,
            "last_event_today": last_event.isoformat() if last_event else None,
            "peak_hour_today": peak_hour,
            "busiest_source_today": busiest_source,
            "sources_today": sources,
            "hourly_today": hourly,
            "daily_trend": daily,
            "recent_events": recent,
            "estimated_cost_today_usd": round(today_count * aws_price_per_1000_images / 1000.0, 4),
        }

    def purge_older_than(self, days: int) -> int:
        threshold = datetime.now(timezone.utc) - timedelta(days=days)
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM analyses WHERE created_at < ?", (threshold.isoformat(),)
            )
            return cursor.rowcount

    def clear(self) -> int:
        with self._lock, self._connect() as conn:
            cursor = conn.execute("DELETE FROM analyses")
            return cursor.rowcount

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
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
            "processing_ms", "duplicate_of", "retained_path", "result_json", "error",
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
        return {
            "total": total,
            "today": today_count,
            "successful": successful,
            "duplicates": duplicates,
            "errors": errors,
            "average_processing_ms": round(avg_ms or 0, 1),
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

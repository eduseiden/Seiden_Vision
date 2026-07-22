from __future__ import annotations

import json
import math
import sqlite3
import threading
from calendar import monthrange
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


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
            conn.execute("""
                CREATE TABLE IF NOT EXISTS analyses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT,
                    created_at TEXT NOT NULL,
                    captured_at TEXT,
                    source TEXT NOT NULL,
                    person TEXT,
                    image_url TEXT NOT NULL,
                    image_hash TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    status TEXT NOT NULL,
                    error_category TEXT,
                    operational_event INTEGER NOT NULL DEFAULT 1,
                    face_count INTEGER NOT NULL DEFAULT 0,
                    dominant_emotion TEXT,
                    confidence REAL,
                    brightness REAL,
                    sharpness REAL,
                    processing_ms INTEGER,
                    download_ms INTEGER,
                    database_ms INTEGER,
                    ha_publish_ms INTEGER,
                    total_ms INTEGER,
                    quality_score REAL,
                    alert_level TEXT,
                    duplicate_of INTEGER,
                    retained_path TEXT,
                    result_json TEXT NOT NULL,
                    error TEXT
                )
            """)
            # Migrate existing databases before creating indexes that depend on new columns.
            # On a fresh database, CREATE TABLE above already contains every column. On an
            # upgraded 0.3.1 database, CREATE TABLE IF NOT EXISTS does not alter the schema.
            existing = {row[1] for row in conn.execute("PRAGMA table_info(analyses)").fetchall()}
            for column, definition in {
                "event_id": "TEXT", "error_category": "TEXT", "operational_event": "INTEGER NOT NULL DEFAULT 1",
                "download_ms": "INTEGER", "database_ms": "INTEGER", "ha_publish_ms": "INTEGER",
                "total_ms": "INTEGER", "quality_score": "REAL", "alert_level": "TEXT",
            }.items():
                if column not in existing:
                    conn.execute(f"ALTER TABLE analyses ADD COLUMN {column} {definition}")

            conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_hash_created ON analyses(image_hash, created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_created ON analyses(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_analyses_event_id ON analyses(event_id)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS provider_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    operation TEXT NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_provider_usage_created ON provider_usage(provider, created_at)")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at)")

    @staticmethod
    def _safe_timezone(name: str) -> ZoneInfo:
        try:
            return ZoneInfo(name)
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    @staticmethod
    def _parse_dt(raw: Any) -> datetime:
        try:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)

    def find_recent_duplicate(self, image_hash: str, minutes: int) -> dict[str, Any] | None:
        if minutes <= 0:
            return None
        threshold = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        with self._connect() as conn:
            row = conn.execute("""
                SELECT * FROM analyses WHERE image_hash=? AND created_at>=? AND status='success'
                ORDER BY id DESC LIMIT 1
            """, (image_hash, threshold.isoformat())).fetchone()
        return dict(row) if row else None

    def is_operational_event(self, person: str | None, source: str, cooldown_seconds: int) -> bool:
        if cooldown_seconds <= 0 or not person or person.strip().lower() in {"unknown", "unavailable", "none", "não identificada"}:
            return True
        threshold = datetime.now(timezone.utc) - timedelta(seconds=cooldown_seconds)
        with self._connect() as conn:
            row = conn.execute("""
                SELECT 1 FROM analyses WHERE status='success' AND operational_event=1
                  AND person=? AND source=? AND created_at>=? ORDER BY id DESC LIMIT 1
            """, (person.strip(), source, threshold.isoformat())).fetchone()
        return row is None

    def insert(self, record: dict[str, Any]) -> int:
        payload = dict(record)
        payload["result_json"] = json.dumps(payload.get("result", {}), ensure_ascii=False, separators=(",", ":"))
        columns = [
            "event_id", "created_at", "captured_at", "source", "person", "image_url", "image_hash", "provider",
            "status", "error_category", "operational_event", "face_count", "dominant_emotion", "confidence",
            "brightness", "sharpness", "processing_ms", "download_ms", "database_ms", "ha_publish_ms", "total_ms",
            "quality_score", "alert_level", "duplicate_of", "retained_path", "result_json", "error",
        ]
        values = [payload.get(c) for c in columns]
        with self._lock, self._connect() as conn:
            cursor = conn.execute(f"INSERT INTO analyses ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})", values)
            return int(cursor.lastrowid)

    def update_timings(self, record_id: int, *, database_ms: int | None = None, ha_publish_ms: int | None = None, total_ms: int | None = None) -> None:
        fields, values = [], []
        for name, value in (("database_ms", database_ms), ("ha_publish_ms", ha_publish_ms), ("total_ms", total_ms)):
            if value is not None:
                fields.append(f"{name}=?"); values.append(value)
        if not fields:
            return
        values.append(record_id)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE analyses SET {','.join(fields)} WHERE id=?", values)

    def list_analyses(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM analyses ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try: item["result"] = json.loads(item.pop("result_json"))
            except (json.JSONDecodeError, TypeError): item["result"] = {}
            result.append(item)
        return result

    def stats(self) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._connect() as conn:
            vals = {
                "total": conn.execute("SELECT COUNT(*) FROM analyses").fetchone()[0],
                "today": conn.execute("SELECT COUNT(*) FROM analyses WHERE substr(created_at,1,10)=?", (today,)).fetchone()[0],
                "successful": conn.execute("SELECT COUNT(*) FROM analyses WHERE status='success'").fetchone()[0],
                "duplicates": conn.execute("SELECT COUNT(*) FROM analyses WHERE status='duplicate'").fetchone()[0],
                "errors": conn.execute("SELECT COUNT(*) FROM analyses WHERE status='error'").fetchone()[0],
                "alerts": conn.execute("SELECT COUNT(*) FROM analyses WHERE alert_level IN ('warning','critical')").fetchone()[0],
            }
            for key, field in (("average_processing_ms","processing_ms"),("average_total_ms","total_ms"),("average_quality_score","quality_score")):
                vals[key] = round(conn.execute(f"SELECT AVG({field}) FROM analyses WHERE status='success'").fetchone()[0] or 0, 1)
        return vals

    def record_provider_call(self, provider: str, operation: str = "analyze") -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("INSERT INTO provider_usage (created_at,provider,operation) VALUES (?,?,?)", (datetime.now(timezone.utc).isoformat(), provider, operation))
            return int(cur.lastrowid)

    def provider_calls_between(self, provider: str, start_utc: datetime, end_utc: datetime) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM provider_usage WHERE provider=? AND created_at>=? AND created_at<?", (provider, start_utc.isoformat(), end_utc.isoformat())).fetchone()[0])

    def provider_calls_today(self, provider: str) -> int:
        now = datetime.now(timezone.utc); start = datetime.combine(now.date(), datetime.min.time(), timezone.utc)
        return self.provider_calls_between(provider, start, start + timedelta(days=1))

    def audit(self, event_type: str, severity: str, message: str, details: dict[str, Any] | None = None) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("INSERT INTO audit_log (created_at,event_type,severity,message,details_json) VALUES (?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), event_type, severity, message, json.dumps(details or {}, ensure_ascii=False)))
            return int(cur.lastrowid)

    def list_audit(self, limit: int = 50) -> list[dict[str, Any]]:
        limit = max(1, min(limit, 500))
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out=[]
        for row in rows:
            item=dict(row)
            try: item["details"] = json.loads(item.pop("details_json"))
            except Exception: item["details"] = {}
            out.append(item)
        return out

    def error_breakdown_today(self, timezone_name: str) -> dict[str, int]:
        tz=self._safe_timezone(timezone_name); now=datetime.now(timezone.utc).astimezone(tz)
        start=datetime.combine(now.date(), datetime.min.time(), tz).astimezone(timezone.utc); end=start+timedelta(days=1)
        with self._connect() as conn:
            rows=conn.execute("SELECT COALESCE(error_category,'unknown') category,COUNT(*) count FROM analyses WHERE status='error' AND created_at>=? AND created_at<? GROUP BY category", (start.isoformat(),end.isoformat())).fetchall()
        return {r["category"]: int(r["count"]) for r in rows}

    @staticmethod
    def _percentile(values: list[float], p: float) -> float:
        if not values: return 0.0
        values=sorted(values); k=(len(values)-1)*p; f=math.floor(k); c=math.ceil(k)
        if f==c: return round(values[int(k)],1)
        return round(values[f]*(c-k)+values[c]*(k-f),1)

    def _management_rows(self, days: int = 70) -> list[dict[str, Any]]:
        threshold=datetime.now(timezone.utc)-timedelta(days=max(2,days))
        with self._connect() as conn:
            rows=conn.execute("""SELECT id,event_id,created_at,captured_at,source,person,status,error_category,operational_event,face_count,quality_score,alert_level,processing_ms,download_ms,database_ms,ha_publish_ms,total_ms,image_url,retained_path,dominant_emotion FROM analyses WHERE created_at>=? ORDER BY created_at ASC""",(threshold.isoformat(),)).fetchall()
        return [dict(r) for r in rows]

    def management_stats(self, timezone_name: str="America/Sao_Paulo", trend_days: int=14, aws_price_per_1000_images: float=1.0, aws_monthly_budget_usd: float=5.0) -> dict[str, Any]:
        tz=self._safe_timezone(timezone_name); now_local=datetime.now(timezone.utc).astimezone(tz); today=now_local.date(); yesterday=today-timedelta(days=1)
        trend_days=max(7,min(int(trend_days),90)); rows=self._management_rows(max(trend_days+40,70))
        def local_dt(r): return self._parse_dt(r.get("captured_at") or r.get("created_at")).astimezone(tz)
        normalized=[(r,local_dt(r)) for r in rows]; successes=[(r,dt) for r,dt in normalized if r.get("status")=="success"]
        captures_today=[(r,dt) for r,dt in successes if dt.date()==today]; events_today_rows=[(r,dt) for r,dt in captures_today if int(r.get("operational_event") or 0)==1]
        yesterday_rows=[(r,dt) for r,dt in successes if dt.date()==yesterday and int(r.get("operational_event") or 0)==1]
        def people(items): return sorted({str(r.get("person")).strip() for r,_ in items if r.get("person") and str(r.get("person")).strip().lower() not in {"unknown","unavailable","none"}})
        def avg(items,field):
            vals=[float(r[field]) for r,_ in items if r.get(field) is not None]; return round(sum(vals)/len(vals),1) if vals else 0.0
        def count_alerts(items): return sum(1 for r,_ in items if r.get("alert_level") in ("warning","critical"))
        today_count=len(events_today_rows); yesterday_count=len(yesterday_rows); variation=round((today_count-yesterday_count)*100/yesterday_count,1) if yesterday_count else (100.0 if today_count else 0.0)
        daily=[]; hist=[]
        for off in range(trend_days-1,-1,-1):
            day=today-timedelta(days=off); items=[(r,dt) for r,dt in successes if dt.date()==day and int(r.get("operational_event") or 0)==1]; count=len(items)
            if day<today: hist.append(count)
            daily.append({"date":day.isoformat(),"events":count,"captures":sum(1 for r,dt in successes if dt.date()==day),"unique_people":len(people(items)),"alerts":count_alerts(items),"average_quality":avg(items,"quality_score"),"average_total_ms":avg(items,"total_ms")})
        avg7=round(sum(hist[-7:])/len(hist[-7:]),1) if hist[-7:] else 0.0; vs7=round((today_count-avg7)*100/avg7,1) if avg7 else (100.0 if today_count else 0.0)
        hour_counts={h:0 for h in range(24)}
        for _,dt in events_today_rows: hour_counts[dt.hour]+=1
        hourly=[{"hour":f"{h:02d}:00","events":hour_counts[h]} for h in range(24)]; peak=max(hour_counts,key=hour_counts.get) if today_count else None
        sc:dict[str,int]={}; pc:dict[str,int]={}
        for r,_ in events_today_rows:
            s=str(r.get("source") or "Não informada"); p=str(r.get("person") or "Não identificada"); sc[s]=sc.get(s,0)+1; pc[p]=pc.get(p,0)+1
        sources=[{"source":k,"events":v} for k,v in sorted(sc.items(),key=lambda x:(-x[1],x[0]))]; persons=[{"person":k,"events":v} for k,v in sorted(pc.items(),key=lambda x:(-x[1],x[0]))]
        recent=[{"id":r.get("id"),"event_id":r.get("event_id"),"time":dt.isoformat(),"person":r.get("person"),"source":r.get("source"),"quality_score":r.get("quality_score"),"alert_level":r.get("alert_level"),"image_url":r.get("image_url"),"emotion":r.get("dominant_emotion"),"operational_event":bool(r.get("operational_event"))} for r,dt in sorted(captures_today,key=lambda x:x[1],reverse=True)[:20]]
        total_times=[float(r["total_ms"]) for r,_ in captures_today if r.get("total_ms") is not None]
        # Cost windows in operational timezone
        day_start=datetime.combine(today,datetime.min.time(),tz); week_start=day_start-timedelta(days=day_start.weekday()); month_start=day_start.replace(day=1)
        next_day=day_start+timedelta(days=1); next_month=(month_start.replace(day=28)+timedelta(days=4)).replace(day=1)
        calls_today=self.provider_calls_between("aws_rekognition",day_start.astimezone(timezone.utc),next_day.astimezone(timezone.utc))
        calls_week=self.provider_calls_between("aws_rekognition",week_start.astimezone(timezone.utc),(now_local+timedelta(seconds=1)).astimezone(timezone.utc))
        calls_month=self.provider_calls_between("aws_rekognition",month_start.astimezone(timezone.utc),(now_local+timedelta(seconds=1)).astimezone(timezone.utc))
        price=float(aws_price_per_1000_images); cost_today=round(calls_today*price/1000,4); cost_week=round(calls_week*price/1000,4); cost_month=round(calls_month*price/1000,4)
        days_elapsed=max(1,today.day); days_month=monthrange(today.year,today.month)[1]; projected=round(cost_month/days_elapsed*days_month,4); budget=float(aws_monthly_budget_usd or 0)
        projected_pct=round(projected*100/budget,1) if budget>0 else 0.0
        budget_status="ok" if projected_pct<70 else "attention" if projected_pct<90 else "warning" if projected_pct<=100 else "critical"
        total_today=len(captures_today)+sum(1 for r,dt in normalized if dt.date()==today and r.get("status") in {"error","duplicate"}); errors=sum(1 for r,dt in normalized if dt.date()==today and r.get("status")=="error"); success_rate=round(len(captures_today)*100/total_today,1) if total_today else 100.0
        last_success=max((dt for r,dt in successes),default=None); last_error=max((dt for r,dt in normalized if r.get("status")=="error"),default=None)
        health="error" if not total_today and last_error else "degraded" if errors or success_rate<95 else "healthy"
        return {
            "timezone":timezone_name,"generated_at":now_local.isoformat(),"health_status":health,"success_rate_today":success_rate,
            "last_success":last_success.isoformat() if last_success else None,"last_error":last_error.isoformat() if last_error else None,"error_breakdown_today":self.error_breakdown_today(timezone_name),
            "captures_today":len(captures_today),"events_today":today_count,"events_yesterday":yesterday_count,"variation_vs_yesterday_percent":variation,"average_events_7d":avg7,"variation_vs_7d_percent":vs7,
            "unique_people_today":len(people(events_today_rows)),"people_today":persons,"alerts_today":count_alerts(captures_today),"no_face_today":sum(1 for r,_ in captures_today if int(r.get("face_count") or 0)==0),"multiple_faces_today":sum(1 for r,_ in captures_today if int(r.get("face_count") or 0)>1),
            "duplicates_today":sum(1 for r,dt in normalized if dt.date()==today and r.get("status")=="duplicate"),"errors_today":errors,"average_quality_today":avg(captures_today,"quality_score"),"average_processing_ms_today":avg(captures_today,"processing_ms"),"average_total_ms_today":avg(captures_today,"total_ms"),"p50_total_ms_today":self._percentile(total_times,.50),"p95_total_ms_today":self._percentile(total_times,.95),
            "average_download_ms_today":avg(captures_today,"download_ms"),"average_database_ms_today":avg(captures_today,"database_ms"),"average_ha_publish_ms_today":avg(captures_today,"ha_publish_ms"),
            "first_event_today":min((dt for _,dt in events_today_rows),default=None).isoformat() if events_today_rows else None,"last_event_today":max((dt for _,dt in events_today_rows),default=None).isoformat() if events_today_rows else None,"peak_hour_today":f"{peak:02d}:00" if peak is not None else "—","busiest_source_today":sources[0]["source"] if sources else "—",
            "sources_today":sources,"hourly_today":hourly,"daily_trend":daily,"recent_events":recent,
            "aws_calls_today":calls_today,"aws_calls_week":calls_week,"aws_calls_month":calls_month,"estimated_cost_today_usd":cost_today,"estimated_cost_week_usd":cost_week,"estimated_cost_month_usd":cost_month,"projected_cost_month_usd":projected,"aws_monthly_budget_usd":budget,"projected_budget_usage_percent":projected_pct,"budget_status":budget_status,
        }

    def purge_older_than(self, days: int) -> int:
        if days <= 0: return 0
        threshold=datetime.now(timezone.utc)-timedelta(days=days)
        with self._lock,self._connect() as conn:
            cur=conn.execute("DELETE FROM analyses WHERE created_at<?",(threshold.isoformat(),)); return cur.rowcount

    def clear(self) -> int:
        with self._lock,self._connect() as conn:
            cur=conn.execute("DELETE FROM analyses"); return cur.rowcount

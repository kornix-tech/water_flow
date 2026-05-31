from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from .models import Calculation, Job


def _dt_to_text(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _text_to_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class JobStore:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    run_name TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    exit_code INTEGER,
                    log_path TEXT NOT NULL,
                    output_dir TEXT NOT NULL,
                    error_message TEXT,
                    calculation_id INTEGER
                )
                """
            )
            existing_columns = {row["name"] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            if "calculation_id" not in existing_columns:
                conn.execute("ALTER TABLE jobs ADD COLUMN calculation_id INTEGER")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS calculations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    input_json TEXT NOT NULL,
                    run_name TEXT UNIQUE,
                    job_id TEXT,
                    status TEXT NOT NULL,
                    result_dir TEXT
                )
                """
            )

    def create(self, job: Job) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, kind, status, command_json, run_name, created_at, started_at,
                    finished_at, exit_code, log_path, output_dir, error_message, calculation_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.id,
                    job.kind,
                    job.status,
                    json.dumps(job.command, ensure_ascii=False),
                    job.run_name,
                    _dt_to_text(job.created_at),
                    _dt_to_text(job.started_at),
                    _dt_to_text(job.finished_at),
                    job.exit_code,
                    job.log_path,
                    job.output_dir,
                    job.error_message,
                    job.calculation_id,
                ),
            )

    def update(self, job_id: str, **fields: object) -> None:
        if not fields:
            return
        allowed = {
            "status",
            "started_at",
            "finished_at",
            "exit_code",
            "error_message",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError(f"Unknown job fields: {sorted(unknown)}")
        columns = []
        values: list[object] = []
        for key, value in fields.items():
            columns.append(f"{key} = ?")
            values.append(_dt_to_text(value) if isinstance(value, datetime) else value)
        values.append(job_id)
        with self._lock, self._connect() as conn:
            conn.execute(f"UPDATE jobs SET {', '.join(columns)} WHERE id = ?", values)

    def get(self, job_id: str) -> Job | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return self._row_to_job(row) if row else None

    def list(self, limit: int = 100) -> list[Job]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_job(row) for row in rows]

    def mark_incomplete_jobs_interrupted(self) -> int:
        timestamp = datetime.utcnow()
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT id, calculation_id FROM jobs WHERE status IN ('queued', 'running')",
            ).fetchall()
            if not rows:
                return 0
            conn.execute(
                """
                UPDATE jobs
                SET status = 'failed',
                    finished_at = ?,
                    error_message = 'Interrupted by server restart'
                WHERE status IN ('queued', 'running')
                """,
                (_dt_to_text(timestamp),),
            )
            calculation_ids = [row["calculation_id"] for row in rows if row["calculation_id"] is not None]
            if calculation_ids:
                placeholders = ",".join("?" for _ in calculation_ids)
                conn.execute(
                    f"""
                    UPDATE calculations
                    SET status = 'failed',
                        updated_at = ?
                    WHERE id IN ({placeholders})
                    """,
                    [_dt_to_text(timestamp), *calculation_ids],
                )
        return len(rows)

    def _row_to_job(self, row: sqlite3.Row) -> Job:
        return Job(
            id=row["id"],
            kind=row["kind"],
            status=row["status"],
            command=json.loads(row["command_json"]),
            run_name=row["run_name"],
            created_at=_text_to_dt(row["created_at"]) or datetime.utcnow(),
            started_at=_text_to_dt(row["started_at"]),
            finished_at=_text_to_dt(row["finished_at"]),
            exit_code=row["exit_code"],
            log_path=row["log_path"],
            output_dir=row["output_dir"],
            error_message=row["error_message"],
            calculation_id=row["calculation_id"],
        )

    def create_calculation(self, input_json: dict, *, now: datetime | None = None) -> Calculation:
        timestamp = now or datetime.utcnow()
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO calculations (
                    title, created_at, updated_at, input_json, run_name, job_id, status, result_dir
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f"расчет №pending-{timestamp.isoformat()}",
                    _dt_to_text(timestamp),
                    _dt_to_text(timestamp),
                    json.dumps(input_json, ensure_ascii=False),
                    None,
                    None,
                    "draft",
                    None,
                ),
            )
            next_id = int(cursor.lastrowid)
            title = f"расчет №{next_id}"
            conn.execute("UPDATE calculations SET title = ? WHERE id = ?", (title, next_id))
        created = self.get_calculation(next_id)
        assert created is not None
        return created

    def get_calculation(self, calculation_id: int) -> Calculation | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM calculations WHERE id = ?", (calculation_id,)).fetchone()
        return self._row_to_calculation(row) if row else None

    def latest_calculation(self) -> Calculation | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM calculations ORDER BY id DESC LIMIT 1").fetchone()
        return self._row_to_calculation(row) if row else None

    def get_calculation_by_run_name(self, run_name: str) -> Calculation | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM calculations WHERE run_name = ?", (run_name,)).fetchone()
        return self._row_to_calculation(row) if row else None

    def list_calculations(self, query: str | None = None, limit: int = 100) -> list[Calculation]:
        sql = "SELECT * FROM calculations"
        params: list[object] = []
        normalized_query = (query or "").strip()
        if normalized_query:
            sql += " WHERE title LIKE ? OR created_at LIKE ? OR run_name LIKE ? OR status LIKE ?"
            like = f"%{normalized_query}%"
            params.extend([like, like, like, like])
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_calculation(row) for row in rows]

    def set_calculation_job(self, calculation_id: int, *, run_name: str, job_id: str, result_dir: str, status: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE calculations
                SET run_name = ?, job_id = ?, result_dir = ?, status = ?, updated_at = ?
                WHERE id = ?
                """,
                (run_name, job_id, result_dir, status, _dt_to_text(datetime.utcnow()), calculation_id),
            )

    def update_calculation_status(self, calculation_id: int, status: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE calculations SET status = ?, updated_at = ? WHERE id = ?",
                (status, _dt_to_text(datetime.utcnow()), calculation_id),
            )

    def delete_calculation(self, calculation_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE jobs SET calculation_id = NULL WHERE calculation_id = ?", (calculation_id,))
            conn.execute("DELETE FROM calculations WHERE id = ?", (calculation_id,))

    def _row_to_calculation(self, row: sqlite3.Row) -> Calculation:
        return Calculation(
            id=row["id"],
            title=row["title"],
            created_at=_text_to_dt(row["created_at"]) or datetime.utcnow(),
            updated_at=_text_to_dt(row["updated_at"]) or datetime.utcnow(),
            input_json=json.loads(row["input_json"]),
            run_name=row["run_name"],
            job_id=row["job_id"],
            status=row["status"],
            result_dir=row["result_dir"],
        )

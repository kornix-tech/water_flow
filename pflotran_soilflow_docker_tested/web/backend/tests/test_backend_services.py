from __future__ import annotations

import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import UTC, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Эти unit-тесты должны запускаться даже в минимальном WSL Python без web-зависимостей.
# Для проверки защитных функций достаточно совместимого исключения HTTPException.
fastapi_stub = types.ModuleType("fastapi")


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fastapi_stub.HTTPException = HTTPException
sys.modules.setdefault("fastapi", fastapi_stub)

from app.file_manager import safe_resolve_under, safe_run_name
from app.job_lifecycle import CALCULATION_STATUS_DRAFT, JOB_STATUS_FAILED, JOB_STATUS_QUEUED
from app.job_store import JobStore
from app.models import Job


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _minimal_workbook_snapshot(value: object, description: str = "Исходное описание") -> dict:
    return {
        "filename": "project_database",
        "updated_at": None,
        "tabs": [
            {
                "id": "project",
                "title": "Проект",
                "kind": "fields",
                "description": None,
                "fields": [
                    {
                        "sheet": "01_Project",
                        "row": 1,
                        "section": None,
                        "key": "project_name",
                        "value": value,
                        "value_type": "str",
                        "unit": None,
                        "description": description,
                        "pflotran": None,
                        "note": None,
                    }
                ],
                "weather": [],
            }
        ],
    }


class PathSafetyTests(unittest.TestCase):
    def test_safe_run_name_accepts_clear_run_ids(self) -> None:
        self.assertEqual(safe_run_name("calculation_000001"), "calculation_000001")

    def test_safe_run_name_rejects_parent_traversal(self) -> None:
        with self.assertRaises(HTTPException):
            safe_run_name("../bad")

    def test_safe_resolve_under_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(HTTPException):
                safe_resolve_under(Path(directory), "../outside.txt")


class JobStoreTests(unittest.TestCase):
    def test_new_database_has_migration_version_and_creates_calculation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.sqlite")
            self.assertEqual(store.schema_version(), 2)

            calculation = store.create_calculation(_minimal_workbook_snapshot("demo"))

            self.assertEqual(calculation.id, 1)
            self.assertEqual(calculation.title, "расчет №1")
            self.assertEqual(calculation.status, CALCULATION_STATUS_DRAFT)

    def test_existing_jobs_table_without_calculation_id_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "jobs.sqlite"
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE jobs (
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
                        error_message TEXT
                    )
                    """
                )

            store = JobStore(db_path)

            with sqlite3.connect(db_path) as conn:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
            self.assertIn("calculation_id", columns)
            self.assertEqual(store.schema_version(), 2)

    def test_soil_curve_tables_are_created_and_cascade_with_calculation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "jobs.sqlite"
            store = JobStore(db_path)
            calculation = store.create_calculation(_minimal_workbook_snapshot("demo"))
            timestamp = _utcnow().isoformat()
            with sqlite3.connect(db_path) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                cursor = conn.execute(
                    """
                    INSERT INTO soil_curve_tables (
                        calculation_id, curve_name, curve_kind, retention_model, conductivity_model,
                        created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (calculation.id, "lab_curve", "retention", "tabular", None, timestamp, timestamp),
                )
                table_id = int(cursor.lastrowid)
                conn.execute(
                    """
                    INSERT INTO soil_curve_points (
                        table_id, point_index, pressure_head_m, water_content, saturation
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (table_id, 0, -0.5, 0.31, 0.72),
                )

            store.delete_calculation(calculation.id)

            with sqlite3.connect(db_path) as conn:
                tables_count = conn.execute("SELECT COUNT(*) FROM soil_curve_tables").fetchone()[0]
                points_count = conn.execute("SELECT COUNT(*) FROM soil_curve_points").fetchone()[0]
            self.assertEqual(tables_count, 0)
            self.assertEqual(points_count, 0)

    def test_restart_marks_active_jobs_failed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.sqlite")
            calculation = store.create_calculation(_minimal_workbook_snapshot("demo"))
            job = Job(
                id="a" * 32,
                kind="calculation",
                status=JOB_STATUS_QUEUED,
                command=["python3", "script.py"],
                run_name="calculation_000001",
                created_at=_utcnow(),
                started_at=None,
                finished_at=None,
                exit_code=None,
                log_path=str(Path(directory) / "job.log"),
                output_dir=str(Path(directory) / "run"),
                error_message=None,
                calculation_id=calculation.id,
            )
            store.create(job)
            store.set_calculation_job(
                calculation.id,
                run_name="calculation_000001",
                job_id=job.id,
                result_dir=str(Path(directory) / "run"),
                status=JOB_STATUS_QUEUED,
            )

            marked_count = store.mark_incomplete_jobs_interrupted()

            self.assertEqual(marked_count, 1)
            self.assertEqual(store.get(job.id).status, JOB_STATUS_FAILED)
            self.assertEqual(store.get_calculation(calculation.id).status, JOB_STATUS_FAILED)


if __name__ == "__main__":
    unittest.main()

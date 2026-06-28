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
from app.services.result_status_artifacts import read_status_artifact_text
from app.services.run_status_overview_service import read_run_status_overview
from app.services.test_run_status_service import read_test_run_status
from app.services.test_suite_summary_service import read_test_suite_status


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

    def test_status_artifact_text_cache_invalidates_on_file_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "TEST_STATUS.txt"
            path.write_text("TEST_STATUS=PASS\n", encoding="utf-8")

            self.assertIn("PASS", read_status_artifact_text(path))

            path.write_text("TEST_STATUS=FAIL\nextra=1\n", encoding="utf-8")

            self.assertIn("FAIL", read_status_artifact_text(path))


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

    def test_soil_curve_store_methods_create_list_get_and_delete_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory) / "jobs.sqlite")
            calculation = store.create_calculation(_minimal_workbook_snapshot("demo"))

            created = store.create_soil_curve_table(
                calculation.id,
                {
                    "curve_name": "lab_retention",
                    "curve_kind": "retention",
                    "retention_model": "tabular",
                    "pressure_unit": "кПа",
                    "saturation_unit": "м3/м3",
                    "comment": "Лабораторная водоудерживающая кривая",
                },
                [
                    {"point_index": 0, "pressure_head_m": -0.1, "water_content": 0.41, "saturation": 0.93},
                    {"point_index": 1, "pressure_head_m": -1.0, "water_content": 0.28, "saturation": 0.64},
                ],
            )

            listed = store.list_soil_curve_tables(calculation.id)
            loaded = store.get_soil_curve_table(int(created["id"]))

            self.assertEqual(len(listed), 1)
            self.assertEqual(loaded["curve_name"], "lab_retention")
            self.assertEqual(len(loaded["points"]), 2)
            self.assertEqual(loaded["points"][0]["point_index"], 0)

            store.delete_soil_curve_table(int(created["id"]))

            self.assertEqual(store.list_soil_curve_tables(calculation.id), [])

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


class TestSuiteSummaryServiceTests(unittest.TestCase):
    def test_read_test_suite_status_prefers_json_and_normalizes_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_SUITE_STATUS.json").write_text(
                """
                {
                  "summary": {
                    "TEST_SUITE_STATUS": "PASS_WITH_WARNINGS",
                    "tests_total": "2",
                    "tests_failed": 0
                  },
                  "results": [
                    {
                      "test_id": "_test_linear_darcy",
                      "status": "PASS",
                      "verification_level": "strict_analytical",
                      "warning_count": "0"
                    }
                  ]
                }
                """,
                encoding="utf-8",
            )

            suite = read_test_suite_status("_test_suite", run_dir)

            self.assertEqual(suite["status"], "PASS_WITH_WARNINGS")
            self.assertEqual(suite["summary"]["tests_total"], 2)
            self.assertEqual(suite["results"][0]["metrics"]["warning_count"], 0)
            self.assertEqual(suite["source"], "TEST_SUITE_STATUS.json")

    def test_read_test_suite_status_uses_csv_rows_with_text_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_SUITE_STATUS.txt").write_text(
                "\n".join(
                    [
                        "TEST_SUITE_STATUS=PASS",
                        "tests_total=1",
                        "tests_failed=0",
                        "",
                        "_test_linear_darcy=PASS",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "TEST_SUITE_RESULTS.csv").write_text(
                "test_id,status,verification_level,warning_count\n"
                "_test_linear_darcy,PASS,strict_analytical,0\n",
                encoding="utf-8",
            )

            suite = read_test_suite_status("_test_suite", run_dir)

            self.assertEqual(suite["summary"]["tests_failed"], 0)
            self.assertEqual(suite["results"][0]["verification_level"], "strict_analytical")
            self.assertIn("TEST_SUITE_RESULTS.csv", suite["files"])

    def test_read_test_suite_status_falls_back_when_json_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_SUITE_STATUS.json").write_text('{"summary": ', encoding="utf-8")
            (run_dir / "TEST_SUITE_STATUS.txt").write_text(
                "TEST_SUITE_STATUS=PASS_WITH_WARNINGS\ntests_total=1\n_test_linear_darcy=PASS\n",
                encoding="utf-8",
            )
            (run_dir / "TEST_SUITE_RESULTS.csv").write_text(
                "test_id,status,verification_level\n_test_linear_darcy,PASS,strict_analytical\n",
                encoding="utf-8",
            )

            suite = read_test_suite_status("_test_suite", run_dir)

            self.assertEqual(suite["status"], "PASS_WITH_WARNINGS")
            self.assertEqual(suite["source"], "TEST_SUITE_STATUS.txt")
            self.assertEqual(suite["summary"]["artifact_readiness"], "PARTIAL")
            self.assertEqual(suite["results"][0]["test_id"], "_test_linear_darcy")

    def test_read_test_suite_status_rejects_symlink_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            outside = Path(directory) / "outside.json"
            outside.write_text("{}", encoding="utf-8")
            (run_dir / "TEST_SUITE_STATUS.json").symlink_to(outside)

            with self.assertRaises(ValueError):
                read_test_suite_status("_test_suite", run_dir)


class TestRunStatusServiceTests(unittest.TestCase):
    def test_read_test_run_status_normalizes_fields_and_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_STATUS.txt").write_text(
                "\n".join(
                    [
                        "TEST_STATUS=PASS_WITH_WARNINGS",
                        "test_id=_test_linear_darcy",
                        "pressure_check=PASS",
                        "solver_diverged=false",
                        "warning_count=1",
                        "q_error_m_s=4.3e-10",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            (run_dir / "test_diagnostics.json").write_text('{"max_rel_pressure_error": 0.001}', encoding="utf-8")

            status = read_test_run_status("_test_linear_darcy", run_dir)

            self.assertEqual(status["status"], "PASS_WITH_WARNINGS")
            self.assertEqual(status["test_id"], "_test_linear_darcy")
            self.assertEqual(status["fields"]["warning_count"], 1)
            self.assertFalse(status["fields"]["solver_diverged"])
            self.assertAlmostEqual(status["fields"]["q_error_m_s"], 4.3e-10)
            self.assertEqual(status["diagnostics"]["max_rel_pressure_error"], 0.001)
            self.assertIn("test_diagnostics.json", status["files"])

    def test_read_test_run_status_keeps_generated_only_message(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_STATUS.txt").write_text(
                "TEST_STATUS=GENERATED_ONLY\nPFLOTRAN executable was not found\n",
                encoding="utf-8",
            )

            status = read_test_run_status("_test_missing_solver", run_dir)

            self.assertEqual(status["status"], "GENERATED_ONLY")
            self.assertEqual(status["messages"], ["PFLOTRAN executable was not found"])

    def test_read_test_run_status_marks_partial_when_status_key_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_STATUS.txt").write_text(
                "test_id=_test_partial\nwriter has not flushed status yet\n",
                encoding="utf-8",
            )

            status = read_test_run_status("_test_partial", run_dir)

            self.assertEqual(status["status"], "UNKNOWN")
            self.assertEqual(status["fields"]["artifact_readiness"], "PARTIAL")
            self.assertEqual(status["messages"], ["writer has not flushed status yet"])

    def test_read_test_run_status_keeps_status_when_diagnostics_json_is_partial(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_STATUS.txt").write_text("TEST_STATUS=PASS\ntest_id=_test_linear_darcy\n", encoding="utf-8")
            (run_dir / "test_diagnostics.json").write_text('{"max_error": ', encoding="utf-8")

            status = read_test_run_status("_test_linear_darcy", run_dir)

            self.assertEqual(status["status"], "PASS")
            self.assertEqual(status["diagnostics"]["artifact_readiness"], "PARTIAL")

    def test_read_test_run_status_rejects_symlink_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            run_dir.mkdir()
            outside = Path(directory) / "outside.txt"
            outside.write_text("TEST_STATUS=PASS\n", encoding="utf-8")
            (run_dir / "TEST_STATUS.txt").symlink_to(outside)

            with self.assertRaises(ValueError):
                read_test_run_status("_test_bad", run_dir)


class RunStatusOverviewServiceTests(unittest.TestCase):
    def test_read_run_status_overview_combines_suite_test_and_visualization_items(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            plots_dir = run_dir / "plots"
            plots_dir.mkdir()
            (run_dir / "TEST_SUITE_STATUS.txt").write_text(
                "TEST_SUITE_STATUS=PASS\ntests_total=1\ntests_passed=1\ntests_failed=0\n_test_linear_darcy=PASS\n",
                encoding="utf-8",
            )
            (run_dir / "TEST_STATUS.txt").write_text(
                "TEST_STATUS=PASS\ntest_id=_test_linear_darcy\npressure_check=PASS\nsolver_check=PASS\ncomparison_points=80\n",
                encoding="utf-8",
            )
            (plots_dir / "VISUALIZATION_STATUS.txt").write_text(
                "VISUALIZATION_STATUS=PASS\nframes_total=12\nprofile_axis=z\ninteractive_html=profiles_animation.html\n",
                encoding="utf-8",
            )

            overview = read_run_status_overview("_test_linear_darcy", run_dir)

            self.assertEqual(overview["run_name"], "_test_linear_darcy")
            self.assertEqual([item["kind"] for item in overview["items"]], ["test-suite", "test-run", "visualization"])
            self.assertEqual(overview["items"][0]["status"], "PASS")
            self.assertEqual(overview["items"][1]["subtitle"], "_test_linear_darcy")
            self.assertEqual(overview["items"][2]["source"], "plots/VISUALIZATION_STATUS.txt")

    def test_read_run_status_overview_has_fallback_for_plain_run_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            overview = read_run_status_overview("plain_run", Path(directory))

            self.assertEqual(len(overview["items"]), 1)
            self.assertEqual(overview["items"][0]["kind"], "run-files")

    def test_read_run_status_overview_uses_json_only_suite_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "TEST_SUITE_STATUS.json").write_text(
                '{"summary": {"TEST_SUITE_STATUS": "PASS", "tests_total": 1, "tests_passed": 1}, "results": []}',
                encoding="utf-8",
            )

            overview = read_run_status_overview("_test_suite", run_dir)

            self.assertEqual(overview["items"][0]["kind"], "test-suite")
            self.assertEqual(overview["items"][0]["source"], "TEST_SUITE_STATUS.json")


if __name__ == "__main__":
    unittest.main()

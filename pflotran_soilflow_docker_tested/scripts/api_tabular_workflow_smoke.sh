#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${WEB_PORT:-18080}"
BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT}}"
KEEP_TABULAR_API_SMOKE="${KEEP_TABULAR_API_SMOKE:-0}"

python3 - "$BASE_URL" "$KEEP_TABULAR_API_SMOKE" <<'PY'
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


base_url = sys.argv[1].rstrip("/")
keep_created_calculation = sys.argv[2] == "1"
api_token = os.environ.get("SOILFLOW_API_TOKEN") or os.environ.get("API_TOKEN") or ""


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if api_token:
        headers["Authorization"] = f"Bearer {api_token}"
    return headers


def request_json(method: str, path: str, payload: object | None = None, expected_statuses: set[int] | None = None) -> object:
    statuses = expected_statuses or {200}
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = _headers()
    if payload is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(f"{base_url}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    if status not in statuses:
        raise SystemExit(f"{path}: unexpected HTTP status {status}, expected {sorted(statuses)}; body={body[:500]}")
    return json.loads(body) if body else {}


def update_workbook_fields(workbook: dict[str, Any], updates: dict[str, object]) -> dict[str, Any]:
    snapshot = json.loads(json.dumps(workbook))
    for key in ("calculation_id", "calculation_title", "calculation_created_at", "calculation_status"):
        snapshot[key] = None
    for tab in snapshot.get("tabs", []):
        if tab.get("kind") != "fields":
            continue
        for field in tab.get("fields", []):
            key = field.get("key")
            if key in updates:
                field["value"] = updates[key]
    return snapshot


def wait_job(job_id: str, *, timeout_seconds: int = 180) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        job = request_json("GET", f"/api/jobs/{job_id}")
        if not isinstance(job, dict):
            raise SystemExit(f"/api/jobs/{job_id}: malformed job payload")
        if job.get("status") in {"success", "failed", "cancelled"}:
            return job
        time.sleep(2)
    raise SystemExit(f"Job {job_id} did not finish in {timeout_seconds} seconds")


def tabular_curves() -> list[dict[str, Any]]:
    return [
        {
            "curve_name": "api_smoke_retention",
            "curve_kind": "retention",
            "retention_model": "tabular",
            "conductivity_model": None,
            "pressure_unit": "Па",
            "saturation_unit": "безразмерная насыщенность",
            "conductivity_unit": "безразмерная",
            "comment": "API smoke Pc(S)",
            "points": [
                {"point_index": 0, "pressure_head_m": None, "pressure_pa": 100000.0, "water_content": None, "saturation": 0.2, "relative_permeability": None, "hydraulic_conductivity_m_s": None, "comment": ""},
                {"point_index": 1, "pressure_head_m": None, "pressure_pa": 20000.0, "water_content": None, "saturation": 0.6, "relative_permeability": None, "hydraulic_conductivity_m_s": None, "comment": ""},
                {"point_index": 2, "pressure_head_m": None, "pressure_pa": 0.0, "water_content": None, "saturation": 1.0, "relative_permeability": None, "hydraulic_conductivity_m_s": None, "comment": ""},
            ],
        },
        {
            "curve_name": "api_smoke_conductivity",
            "curve_kind": "conductivity",
            "retention_model": "tabular",
            "conductivity_model": "tabular",
            "pressure_unit": "Па",
            "saturation_unit": "безразмерная насыщенность",
            "conductivity_unit": "безразмерная",
            "comment": "API smoke kr(S)",
            "points": [
                {"point_index": 0, "pressure_head_m": None, "pressure_pa": None, "water_content": None, "saturation": 0.2, "relative_permeability": 0.0, "hydraulic_conductivity_m_s": None, "comment": ""},
                {"point_index": 1, "pressure_head_m": None, "pressure_pa": None, "water_content": None, "saturation": 0.6, "relative_permeability": 0.25, "hydraulic_conductivity_m_s": None, "comment": ""},
                {"point_index": 2, "pressure_head_m": None, "pressure_pa": None, "water_content": None, "saturation": 1.0, "relative_permeability": 1.0, "hydraulic_conductivity_m_s": None, "comment": ""},
            ],
        },
    ]


calculation_id: int | None = None
run_name: str | None = None

try:
    readiness = request_json("GET", "/api/health/ready")
    if not isinstance(readiness, dict) or readiness.get("status") != "ready":
        raise SystemExit("/api/health/ready: service is not ready")

    workbook = request_json("GET", "/api/inputs/workbook")
    if not isinstance(workbook, dict):
        raise SystemExit("/api/inputs/workbook: malformed workbook")
    smoke_workbook = update_workbook_fields(
        workbook,
        {
            "project_name": f"tabular_api_smoke_{int(time.time())}",
            "retention_model": "tabular",
            "conductivity_model": "tabular",
            "final_time_days": 0.01,
            "maximum_timestep_days": 0.005,
            "output_interval_days": 0.005,
        },
    )
    saved_workbook = request_json("PUT", "/api/inputs/workbook", smoke_workbook)
    if not isinstance(saved_workbook, dict) or not saved_workbook.get("calculation_id"):
        raise SystemExit("/api/inputs/workbook: calculation was not created")
    calculation_id = int(saved_workbook["calculation_id"])

    for curve in tabular_curves():
        request_json("POST", f"/api/soil-curves/calculations/{calculation_id}", curve)

    run_job = request_json("POST", f"/api/calculations/{calculation_id}/run")
    if not isinstance(run_job, dict) or not run_job.get("job_id"):
        raise SystemExit("/api/calculations/{id}/run: malformed job payload")
    finished_run_job = wait_job(str(run_job["job_id"]))
    if finished_run_job.get("status") != "success":
        raise SystemExit(f"Calculation failed: {finished_run_job.get('error_message')}")
    run_name = str(finished_run_job.get("run_name") or "")
    if not run_name:
        raise SystemExit("Calculation finished without run_name")

    visualization_job = request_json("POST", f"/api/jobs/run-visualization/{run_name}")
    if not isinstance(visualization_job, dict) or not visualization_job.get("job_id"):
        raise SystemExit("/api/jobs/run-visualization/{run_name}: malformed job payload")
    finished_visualization_job = wait_job(str(visualization_job["job_id"]))
    if finished_visualization_job.get("status") != "success":
        raise SystemExit(f"Visualization failed: {finished_visualization_job.get('error_message')}")

    runs = request_json("GET", "/api/results/runs")
    if not isinstance(runs, list):
        raise SystemExit("/api/results/runs: response must be a list")
    current_run = next((item for item in runs if isinstance(item, dict) and item.get("run_name") == run_name), None)
    if current_run is None or not current_run.get("has_visualization"):
        raise SystemExit(f"/api/results/runs: visualization marker was not found for {run_name}")

    html_response = urllib.request.Request(f"{base_url}/api/visualization/{run_name}/html", headers=_headers(), method="GET")
    with urllib.request.urlopen(html_response, timeout=30) as response:
        html_text = response.read().decode("utf-8", errors="replace")
    if "<html" not in html_text.lower() or "plot" not in html_text.lower():
        raise SystemExit(f"/api/visualization/{run_name}/html: malformed HTML visualization")

    print(
        "OK: tabular API workflow smoke passed "
        f"calculation_id={calculation_id} run_name={run_name} "
        f"calculation_job_id={finished_run_job['id']} visualization_job_id={finished_visualization_job['id']}"
    )
finally:
    if calculation_id is not None and not keep_created_calculation:
        try:
            request_json("DELETE", f"/api/calculations/{calculation_id}", expected_statuses={200, 404})
        except Exception as exc:  # noqa: BLE001 - cleanup must not hide the primary smoke result.
            print(f"WARN: could not delete smoke calculation {calculation_id}: {exc}", file=sys.stderr)
PY

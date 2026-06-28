#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${WEB_PORT:-18080}"
BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT}}"

python3 - "$BASE_URL" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


base_url = sys.argv[1].rstrip("/")


def get_json(path: str, expected_statuses: set[int] | None = None) -> tuple[int, object]:
    statuses = expected_statuses or {200}
    request = urllib.request.Request(f"{base_url}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode("utf-8")
    if status not in statuses:
        raise SystemExit(f"{path}: unexpected HTTP status {status}, expected {sorted(statuses)}")
    return status, json.loads(payload)


_, health = get_json("/api/health")
if health.get("status") != "ok":
    raise SystemExit("/api/health: status is not ok")

# Readiness может вернуть 503 на неполностью подготовленном окружении; smoke проверяет контракт ответа.
_, readiness = get_json("/api/health/ready", {200, 503})
if "checks" not in readiness or "schema_version" not in readiness:
    raise SystemExit("/api/health/ready: malformed readiness payload")

_, system_info = get_json("/api/system/info")
for key in ("workspace", "pflotran_exe", "frontend_available"):
    if key not in system_info:
        raise SystemExit(f"/api/system/info: missing {key}")

_, workbook = get_json("/api/inputs/workbook")
if not isinstance(workbook.get("tabs"), list):
    raise SystemExit("/api/inputs/workbook: tabs must be a list")

_, calculations = get_json("/api/calculations")
if not isinstance(calculations, list):
    raise SystemExit("/api/calculations: response must be a list")
if calculations:
    calculation_id = calculations[0].get("id")
    _, soil_curves = get_json(f"/api/soil-curves/calculations/{calculation_id}")
    if not isinstance(soil_curves, list):
        raise SystemExit("/api/soil-curves/calculations/{id}: response must be a list")

_, runs = get_json("/api/results/runs")
if not isinstance(runs, list):
    raise SystemExit("/api/results/runs: response must be a list")

overview_run = None
for run in runs:
    if not isinstance(run, dict):
        raise SystemExit("/api/results/runs: each run must be an object")
    run_name = run.get("run_name")
    if not isinstance(run_name, str) or not run_name:
        raise SystemExit("/api/results/runs: each run must have a run_name")
    if run.get("has_test_status") or run.get("has_suite_status") or run.get("has_visualization"):
        overview_run = run_name
        break

if overview_run is None and runs:
    # Даже обычная папка результата должна отдавать fallback-карточку run-files.
    overview_run = runs[0]["run_name"]

if overview_run is not None:
    _, overview = get_json(f"/api/results/runs/{overview_run}/overview")
    if overview.get("run_name") != overview_run:
        raise SystemExit("/api/results/runs/{run}/overview: unexpected run_name")
    items = overview.get("items")
    if not isinstance(items, list) or not items:
        raise SystemExit("/api/results/runs/{run}/overview: items must be a non-empty list")
    for item in items:
        if not isinstance(item, dict):
            raise SystemExit("/api/results/runs/{run}/overview: each item must be an object")
        for key in ("kind", "title", "status"):
            if not item.get(key):
                raise SystemExit(f"/api/results/runs/{{run}}/overview: item is missing {key}")
else:
    print("/api/results/runs/{run}/overview: skipped because there are no runs")

print(f"OK: API smoke passed for {base_url}")
PY

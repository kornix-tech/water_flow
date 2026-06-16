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

_, runs = get_json("/api/results/runs")
if not isinstance(runs, list):
    raise SystemExit("/api/results/runs: response must be a list")

print(f"OK: API smoke passed for {base_url}")
PY

#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${WEB_PORT:-18080}"
BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT}}"
SMOKE_JOB_ID="${SMOKE_JOB_ID:-eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee}"

cleanup() {
  WEB_PORT="$WEB_PORT" docker compose exec -T -e SMOKE_JOB_ID="$SMOKE_JOB_ID" soilflow-web python3 - <<'PY' >/dev/null 2>&1 || true
import os
import sqlite3
from pathlib import Path

db_path = Path("/workspace/jobs.sqlite")
if db_path.exists():
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM jobs WHERE id = ?", (os.environ["SMOKE_JOB_ID"],))
PY
}
trap cleanup EXIT

WEB_PORT="$WEB_PORT" docker compose exec -T -e SMOKE_JOB_ID="$SMOKE_JOB_ID" soilflow-web python3 - <<'PY'
import datetime as dt
import json
import os
import sqlite3
from pathlib import Path

job_id = os.environ["SMOKE_JOB_ID"]
jobs_dir = Path("/workspace/jobs") / job_id
jobs_dir.mkdir(parents=True, exist_ok=True)
log_path = jobs_dir / "job.log"
log_path.write_text("restart resilience smoke placeholder\n", encoding="utf-8")
now = dt.datetime.now(dt.UTC).replace(tzinfo=None, microsecond=0).isoformat()
with sqlite3.connect("/workspace/jobs.sqlite") as conn:
    conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    conn.execute(
        """
        INSERT INTO jobs (
            id, kind, status, command_json, run_name, created_at, started_at,
            finished_at, exit_code, log_path, output_dir, error_message, calculation_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            job_id,
            "restart-smoke",
            "queued",
            json.dumps(["restart-smoke"]),
            "_restart_smoke",
            now,
            None,
            None,
            None,
            str(log_path),
            "/workspace/tmp/restart_smoke",
            None,
            None,
        ),
    )
PY

WEB_PORT="$WEB_PORT" docker compose restart soilflow-web >/dev/null
for attempt in $(seq 1 30); do
  if curl -fsS "${BASE_URL}/api/health" >/dev/null 2>&1; then
    break
  fi
  if [[ "$attempt" -eq 30 ]]; then
    echo "API health check failed after restart" >&2
    exit 1
  fi
  sleep 1
done

python3 - "$BASE_URL" "$SMOKE_JOB_ID" <<'PY'
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

base_url = sys.argv[1].rstrip("/")
job_id = sys.argv[2]


def get_json(path: str, expected_status: int = 200) -> object:
    request = urllib.request.Request(f"{base_url}{path}", headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status = response.status
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        payload = exc.read().decode("utf-8")
    if status != expected_status:
        raise SystemExit(f"{path}: unexpected HTTP status {status}, expected {expected_status}")
    return json.loads(payload)


ready = get_json("/api/health/ready")
if ready.get("status") != "ready" or ready.get("schema_version") != 2:
    raise SystemExit("/api/health/ready: service is not ready after restart")

job = get_json(f"/api/jobs/{job_id}")
if job.get("status") != "failed":
    raise SystemExit("/api/jobs/{id}: queued smoke job was not marked failed after restart")
if job.get("error_message") != "Interrupted by server restart":
    raise SystemExit("/api/jobs/{id}: unexpected restart error message")
if not job.get("finished_at"):
    raise SystemExit("/api/jobs/{id}: finished_at was not set")

calculations = get_json("/api/calculations")
if not isinstance(calculations, list):
    raise SystemExit("/api/calculations: response must be a list after restart")

print(f"OK: restart resilience smoke passed for {base_url}")
PY

#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${WEB_PORT:-18080}"
BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT}}"
PERF_RUNS="${PERF_RUNS:-40}"
PERF_FILES_PER_RUN="${PERF_FILES_PER_RUN:-30}"
LIST_MAX_SECONDS="${LIST_MAX_SECONDS:-2.5}"
DETAIL_MAX_SECONDS="${DETAIL_MAX_SECONDS:-1.5}"
OVERVIEW_MAX_SECONDS="${OVERVIEW_MAX_SECONDS:-1.5}"

cleanup() {
  WEB_PORT="$WEB_PORT" docker compose exec -T soilflow-web python3 - <<'PY' >/dev/null 2>&1 || true
from pathlib import Path
import shutil

runs_dir = Path("/workspace/output/runs")
for path in runs_dir.glob("_perf_smoke_*"):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
PY
}
trap cleanup EXIT

WEB_PORT="$WEB_PORT" docker compose exec -T \
  -e PERF_RUNS="$PERF_RUNS" \
  -e PERF_FILES_PER_RUN="$PERF_FILES_PER_RUN" \
  soilflow-web python3 - <<'PY'
from pathlib import Path
import os
import shutil

runs_dir = Path("/workspace/output/runs")
runs_dir.mkdir(parents=True, exist_ok=True)
run_count = int(os.environ["PERF_RUNS"])
files_per_run = int(os.environ["PERF_FILES_PER_RUN"])

for index in range(run_count):
    run_dir = runs_dir / f"_perf_smoke_{index:03d}"
    if run_dir.exists() and not run_dir.is_symlink():
        shutil.rmtree(run_dir)
    nested_dir = run_dir / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "TEST_STATUS.txt").write_text(
        f"TEST_STATUS=PASS\ntest_id={run_dir.name}\ncomparison_points=1\n",
        encoding="utf-8",
    )
    (run_dir / "TEST_SUITE_STATUS.txt").write_text(
        "TEST_SUITE_STATUS=PASS\ntests_total=1\ntests_passed=1\ntests_failed=0\n",
        encoding="utf-8",
    )
    (run_dir / "TEST_SUITE_STATUS.json").write_text(
        '{"summary": {"TEST_SUITE_STATUS": "PASS", "tests_total": 1, "tests_passed": 1}, "results": []}\n',
        encoding="utf-8",
    )
    for file_index in range(files_per_run):
        (nested_dir / f"payload_{file_index:03d}.txt").write_text("x" * 128, encoding="utf-8")
PY

python3 - "$BASE_URL" "$LIST_MAX_SECONDS" "$DETAIL_MAX_SECONDS" "$OVERVIEW_MAX_SECONDS" <<'PY'
from __future__ import annotations

import json
import sys
import time
import urllib.request

base_url = sys.argv[1].rstrip("/")
list_max_seconds = float(sys.argv[2])
detail_max_seconds = float(sys.argv[3])
overview_max_seconds = float(sys.argv[4])
target_run = "_perf_smoke_000"


def get_json(path: str, max_seconds: float) -> object:
    start = time.perf_counter()
    with urllib.request.urlopen(f"{base_url}{path}", timeout=max(10.0, max_seconds + 5.0)) as response:
        payload = response.read().decode("utf-8")
    elapsed = time.perf_counter() - start
    if elapsed > max_seconds:
        raise SystemExit(f"{path}: {elapsed:.3f}s exceeds {max_seconds:.3f}s")
    return json.loads(payload)


runs = get_json("/api/results/runs", list_max_seconds)
if not isinstance(runs, list):
    raise SystemExit("/api/results/runs: response must be a list")
run = next((item for item in runs if isinstance(item, dict) and item.get("run_name") == target_run), None)
if run is None:
    raise SystemExit(f"/api/results/runs: missing {target_run}")
if run.get("files") != []:
    raise SystemExit("/api/results/runs: summary endpoint must not include per-run file list")
if not run.get("has_test_status") or not run.get("has_suite_status"):
    raise SystemExit("/api/results/runs: status flags are missing for performance smoke run")

detail = get_json(f"/api/results/runs/{target_run}", detail_max_seconds)
if not detail.get("files"):
    raise SystemExit("/api/results/runs/{run}: detailed endpoint must include selected run files")

overview = get_json(f"/api/results/runs/{target_run}/overview", overview_max_seconds)
kinds = {item.get("kind") for item in overview.get("items", []) if isinstance(item, dict)}
if "test-suite" not in kinds or "test-run" not in kinds:
    raise SystemExit("/api/results/runs/{run}/overview: missing status items")

test_status = get_json(f"/api/results/runs/{target_run}/test-status", detail_max_seconds)
if test_status.get("status") != "PASS":
    raise SystemExit("/api/results/runs/{run}/test-status: unexpected status")

suite_status = get_json(f"/api/results/runs/{target_run}/test-suite", detail_max_seconds)
if suite_status.get("status") != "PASS":
    raise SystemExit("/api/results/runs/{run}/test-suite: unexpected status")

print(f"OK: results performance smoke passed for {base_url}")
PY

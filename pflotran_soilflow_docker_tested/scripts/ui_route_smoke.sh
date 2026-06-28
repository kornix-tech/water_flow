#!/usr/bin/env bash
set -euo pipefail

WEB_PORT="${WEB_PORT:-18080}"
BASE_URL="${BASE_URL:-http://localhost:${WEB_PORT}}"

python3 - "$BASE_URL" <<'PY'
from __future__ import annotations

import html.parser
import sys
import urllib.error
import urllib.parse
import urllib.request


base_url = sys.argv[1].rstrip("/")
routes = ("/", "/ishodnye", "/status", "/testy", "/raschety", "/grafiki", "/sistema")


class AssetParser(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.assets: set[str] = set()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name: value for name, value in attrs if value}
        if tag == "script" and "src" in attr_map:
            self.assets.add(attr_map["src"])
        if tag == "link" and attr_map.get("rel") == "stylesheet" and "href" in attr_map:
            self.assets.add(attr_map["href"])


def request(path: str, method: str = "GET", expected_statuses: set[int] | None = None) -> tuple[int, str, dict[str, str]]:
    statuses = expected_statuses or {200}
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, method=method, headers={"Accept": "text/html,application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status = response.status
            body = response.read().decode("utf-8", errors="replace")
            headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")
        headers = dict(exc.headers.items())
    if status not in statuses:
        raise SystemExit(f"{method} {path}: unexpected HTTP status {status}, expected {sorted(statuses)}")
    return status, body, headers


def get_header(headers: dict[str, str], name: str) -> str:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def assert_frontend_html(path: str, body: str, headers: dict[str, str]) -> None:
    content_type = get_header(headers, "Content-Type")
    if "text/html" not in content_type:
        raise SystemExit(f"{path}: expected text/html, got {content_type!r}")
    if '<div id="root">' not in body:
        raise SystemExit(f"{path}: frontend root element was not found")
    if "Влагоперенос в почве" not in body:
        raise SystemExit(f"{path}: expected application title was not found")
    if not get_header(headers, "Content-Security-Policy"):
        raise SystemExit(f"{path}: missing Content-Security-Policy header")


_, index_body, index_headers = request("/")
assert_frontend_html("/", index_body, index_headers)

parser = AssetParser()
parser.feed(index_body)
if not parser.assets:
    raise SystemExit("/: frontend asset references were not found")

for asset in sorted(parser.assets):
    parsed = urllib.parse.urlparse(asset)
    if parsed.scheme or parsed.netloc:
        raise SystemExit(f"/: frontend asset must be same-origin, got {asset}")
    status, _, headers = request(asset)
    content_type = get_header(headers, "Content-Type")
    if asset.endswith(".js") and "javascript" not in content_type:
        raise SystemExit(f"{asset}: expected javascript content type, got {content_type!r}")
    if asset.endswith(".css") and "text/css" not in content_type:
        raise SystemExit(f"{asset}: expected css content type, got {content_type!r}")

for route in routes:
    _, body, headers = request(route)
    assert_frontend_html(route, body, headers)

# SPA fallback не должен маскировать неизвестные API URL как index.html.
status, body, headers = request("/api/__ui_route_smoke_missing__", expected_statuses={404})
content_type = get_header(headers, "Content-Type")
if "application/json" not in content_type:
    raise SystemExit(f"/api/__ui_route_smoke_missing__: expected JSON 404, got {content_type!r}")

print(f"OK: UI route smoke passed for {base_url}")
PY

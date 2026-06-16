from __future__ import annotations

import hmac
import threading
import time
from collections import deque
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import ensure_workspace, load_settings
from .file_manager import FileManager
from .job_manager import JobManager
from .job_store import JobStore
from .routers import calculations, files, health, inputs, jobs, projects, results, soil_curves, system, visualization


FRONTEND_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self'; "
    "frame-src 'self' blob:; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "form-action 'self'; "
    "frame-ancestors 'self'"
)


class RateLimiter:
    def __init__(self, requests_per_minute: int) -> None:
        self.requests_per_minute = requests_per_minute
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - 60
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] < window_start:
                hits.popleft()
            if len(hits) >= self.requests_per_minute:
                return False
            hits.append(now)
            return True


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            if path == "api" or path.startswith("api/"):
                raise
            index_path = Path(self.directory) / "index.html"
            if index_path.exists():
                return FileResponse(index_path)
            raise


settings = load_settings()
ensure_workspace(settings)

app = FastAPI(
    title="SoilFlow PFLOTRAN Web",
    docs_url="/api/docs" if settings.enable_api_docs else None,
    redoc_url=None,
    openapi_url="/api/openapi.json" if settings.enable_api_docs else None,
)
app.state.settings = settings
app.state.file_manager = FileManager(settings)
app.state.job_store = JobStore(settings.database_path)
# После рестарта контейнера дочерние процессы уже остановлены, поэтому не оставляем
# старые queued/running записи висеть в интерфейсе как активные задачи.
app.state.job_store.mark_incomplete_jobs_interrupted()
app.state.job_manager = JobManager(settings, app.state.job_store)
app.state.rate_limiter = RateLimiter(settings.api_rate_limit_per_minute)


@app.middleware("http")
async def token_auth_middleware(request: Request, call_next):
    is_api_request = request.url.path == "/api" or request.url.path.startswith("/api/")
    if is_api_request:
        content_length = request.headers.get("content-length")
        if content_length and content_length.isdigit():
            if int(content_length) > settings.max_json_body_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request body is too large"})
        client_host = request.client.host if request.client else "unknown"
        if not request.app.state.rate_limiter.allow(client_host):
            return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    if is_api_request and settings.auth_mode == "token":
        expected = f"Bearer {settings.api_token}" if settings.api_token else None
        provided = request.headers.get("authorization", "")
        cookie_token = request.cookies.get("soilflow_api_token", "")
        visualization_html_request = (
            request.method == "GET"
            and request.url.path.startswith("/api/visualization/")
            and request.url.path.endswith("/html")
        )
        cookie_expected = settings.api_token or ""
        cookie_allowed = visualization_html_request and cookie_expected and hmac.compare_digest(cookie_token, cookie_expected)
        if not expected or (not hmac.compare_digest(provided, expected) and not cookie_allowed):
            return JSONResponse(status_code=401, content={"detail": "Invalid or missing API token"})
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
    response.headers.setdefault("Content-Security-Policy", FRONTEND_CSP)
    if settings.enable_hsts:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    if is_api_request:
        response.headers.setdefault("Cache-Control", "no-store")
    elif request.url.path.startswith("/assets/"):
        response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
    else:
        response.headers.setdefault("Cache-Control", "no-store")
    return response


app.include_router(health.router, prefix="/api/health", tags=["health"])
app.include_router(system.router, prefix="/api/system", tags=["system"])
app.include_router(projects.router, prefix="/api/projects", tags=["projects"])
app.include_router(inputs.router, prefix="/api/inputs", tags=["inputs"])
app.include_router(calculations.router, prefix="/api/calculations", tags=["calculations"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(jobs.router, prefix="/api/jobs", tags=["jobs"])
app.include_router(results.router, prefix="/api/results", tags=["results"])
app.include_router(visualization.router, prefix="/api/visualization", tags=["visualization"])
app.include_router(soil_curves.router, prefix="/api/soil-curves", tags=["soil-curves"])

frontend_dist = settings.soilflow_home / "web" / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", SPAStaticFiles(directory=str(frontend_dist), html=True), name="frontend")

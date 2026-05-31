from __future__ import annotations

from fastapi import APIRouter

from ..schemas import HealthResponse

router = APIRouter()


@router.get("", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="soilflow-pflotran-web")

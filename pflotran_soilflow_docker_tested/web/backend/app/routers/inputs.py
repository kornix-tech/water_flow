from __future__ import annotations

from fastapi import APIRouter, Request

from ..schemas import InputWorkbook
from ..services.input_json_service import calculation_to_workbook, read_seed_workbook, workbook_to_json

router = APIRouter()


@router.get("/workbook", response_model=InputWorkbook)
def get_workbook(request: Request) -> InputWorkbook:
    calculation = request.app.state.job_store.latest_calculation()
    if calculation is not None:
        return calculation_to_workbook(calculation)
    return read_seed_workbook(request.app.state.settings.default_input_json)


@router.put("/workbook", response_model=InputWorkbook)
def save_workbook(payload: InputWorkbook, request: Request) -> InputWorkbook:
    calculation = request.app.state.job_store.create_calculation(workbook_to_json(payload))
    return calculation_to_workbook(calculation)


@router.post("/reset", response_model=InputWorkbook)
def reset_workbook(request: Request) -> InputWorkbook:
    return read_seed_workbook(request.app.state.settings.default_input_json)

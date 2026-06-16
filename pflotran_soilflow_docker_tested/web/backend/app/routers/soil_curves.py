from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..schemas import GenericMessage, SoilCurveTableCreate, SoilCurveTableRead

router = APIRouter()


def _job_store(request: Request):
    return request.app.state.job_store


@router.get("/calculations/{calculation_id}", response_model=list[SoilCurveTableRead])
def list_soil_curves(calculation_id: int, request: Request) -> list[SoilCurveTableRead]:
    if _job_store(request).get_calculation(calculation_id) is None:
        raise HTTPException(status_code=404, detail="Расчет не найден")
    return [SoilCurveTableRead.model_validate(item) for item in _job_store(request).list_soil_curve_tables(calculation_id)]


@router.post("/calculations/{calculation_id}", response_model=SoilCurveTableRead)
def create_soil_curve(calculation_id: int, payload: SoilCurveTableCreate, request: Request) -> SoilCurveTableRead:
    if _job_store(request).get_calculation(calculation_id) is None:
        raise HTTPException(status_code=404, detail="Расчет не найден")
    try:
        created = _job_store(request).create_soil_curve_table(
            calculation_id,
            payload.model_dump(exclude={"points"}),
            [point.model_dump() for point in payload.points],
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Не удалось сохранить табличную кривую: {exc}") from exc
    return SoilCurveTableRead.model_validate(created)


@router.get("/{table_id}", response_model=SoilCurveTableRead)
def get_soil_curve(table_id: int, request: Request) -> SoilCurveTableRead:
    curve = _job_store(request).get_soil_curve_table(table_id)
    if curve is None:
        raise HTTPException(status_code=404, detail="Табличная кривая не найдена")
    return SoilCurveTableRead.model_validate(curve)


@router.delete("/{table_id}", response_model=GenericMessage)
def delete_soil_curve(table_id: int, request: Request) -> GenericMessage:
    curve = _job_store(request).get_soil_curve_table(table_id)
    if curve is None:
        raise HTTPException(status_code=404, detail="Табличная кривая не найдена")
    _job_store(request).delete_soil_curve_table(table_id)
    return GenericMessage(status="deleted", detail=f"Табличная кривая {curve['curve_name']} удалена")

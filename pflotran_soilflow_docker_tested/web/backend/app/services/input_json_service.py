from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..models import Calculation
from ..schemas import CalculationRead, CalculationSummary, InputWorkbook


def read_seed_workbook(path: Path) -> InputWorkbook:
    if not path.exists():
        raise HTTPException(status_code=404, detail="JSON-шаблон исходных данных не найден")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"JSON-шаблон исходных данных поврежден: {exc}") from exc
    return InputWorkbook.model_validate(data)


def workbook_to_json(workbook: InputWorkbook) -> dict[str, Any]:
    data = workbook.model_dump(mode="json")
    # Снимок расчета не должен наследовать служебные метки предыдущего сохранения.
    for key in ("calculation_id", "calculation_title", "calculation_created_at", "calculation_status"):
        data.pop(key, None)
    data["filename"] = "project_database"
    data["updated_at"] = datetime.utcnow().isoformat()
    return data


def seed_workbook_to_json(workbook: InputWorkbook) -> dict[str, Any]:
    data = workbook.model_dump(mode="json")
    data["filename"] = "project_database"
    return data


def calculation_to_workbook(calculation: Calculation) -> InputWorkbook:
    data = deepcopy(calculation.input_json)
    data.update(
        {
            "calculation_id": calculation.id,
            "calculation_title": calculation.title,
            "calculation_created_at": calculation.created_at.isoformat(),
            "calculation_status": calculation.status,
            "updated_at": calculation.updated_at.isoformat(),
        }
    )
    return InputWorkbook.model_validate(data)


def calculation_summary(calculation: Calculation) -> CalculationSummary:
    return CalculationSummary(
        id=calculation.id,
        title=calculation.title,
        created_at=calculation.created_at,
        updated_at=calculation.updated_at,
        run_name=calculation.run_name,
        job_id=calculation.job_id,
        status=calculation.status,
        result_dir=calculation.result_dir,
        has_results=bool(calculation.run_name and calculation.result_dir and Path(calculation.result_dir).exists()),
    )


def calculation_read(calculation: Calculation) -> CalculationRead:
    return CalculationRead(**calculation_summary(calculation).model_dump(), input=calculation_to_workbook(calculation))


def write_workbook_json(workbook: InputWorkbook, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(workbook_to_json(workbook), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

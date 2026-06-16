from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from ..models import Calculation
from ..schemas import CalculationRead, CalculationSummary, InputWorkbook


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    return value


def read_seed_workbook(path: Path) -> InputWorkbook:
    if not path.exists():
        raise HTTPException(status_code=404, detail="JSON-шаблон исходных данных не найден")
    try:
        workbook_snapshot = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"JSON-шаблон исходных данных поврежден: {exc}") from exc
    return InputWorkbook.model_validate(workbook_snapshot)


def workbook_to_json(workbook: InputWorkbook, *, soil_curve_tables: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    workbook_snapshot = workbook.model_dump(mode="json")
    # Снимок расчета не должен наследовать служебные метки предыдущего сохранения.
    for key in ("calculation_id", "calculation_title", "calculation_created_at", "calculation_status"):
        workbook_snapshot.pop(key, None)
    workbook_snapshot["filename"] = "project_database"
    workbook_snapshot["updated_at"] = datetime.now(UTC).isoformat()
    if soil_curve_tables is not None:
        # Табличные кривые приходят из SQLite с datetime-объектами; расчетный
        # JSON должен оставаться переносимым plain JSON без backend-типов.
        workbook_snapshot["soil_curve_tables"] = _json_safe_value(soil_curve_tables)
    return workbook_snapshot


def seed_workbook_to_json(workbook: InputWorkbook) -> dict[str, Any]:
    workbook_snapshot = workbook.model_dump(mode="json")
    workbook_snapshot["filename"] = "project_database"
    return workbook_snapshot


def _merge_seed_fields(saved_workbook_snapshot: dict[str, Any], seed_workbook: InputWorkbook | None) -> dict[str, Any]:
    if seed_workbook is None:
        return saved_workbook_snapshot
    merged_workbook_snapshot = deepcopy(saved_workbook_snapshot)
    merged_tabs = merged_workbook_snapshot.get("tabs")
    if not isinstance(merged_tabs, list):
        return merged_workbook_snapshot
    seed_tabs = {tab.id: tab.model_dump(mode="json") for tab in seed_workbook.tabs}
    for index, tab in enumerate(merged_tabs):
        if not isinstance(tab, dict):
            continue
        seed_tab = seed_tabs.get(str(tab.get("id", "")))
        if not seed_tab or tab.get("kind") != "fields":
            continue
        fields = tab.get("fields")
        if not isinstance(fields, list):
            continue
        existing_by_key = {field.get("key"): field for field in fields if isinstance(field, dict)}
        used_keys: set[str] = set()
        merged_fields: list[dict[str, Any]] = []
        for seed_field in seed_tab.get("fields", []):
            key = seed_field.get("key")
            existing = existing_by_key.get(key)
            if isinstance(existing, dict):
                # Сохраняем введенное пользователем значение, но подтягиваем новые
                # описания, типы и порядок полей из актуального шаблона.
                next_field = {**seed_field, "value": existing.get("value", seed_field.get("value"))}
                merged_fields.append(next_field)
                used_keys.add(str(key))
            else:
                merged_fields.append(seed_field)
        merged_fields.extend(field for field in fields if isinstance(field, dict) and str(field.get("key")) not in used_keys)
        merged_tabs[index] = {**tab, "fields": merged_fields}
    return merged_workbook_snapshot


def calculation_to_workbook(calculation: Calculation, seed_workbook: InputWorkbook | None = None) -> InputWorkbook:
    workbook_snapshot = deepcopy(calculation.input_json)
    workbook_snapshot = _merge_seed_fields(workbook_snapshot, seed_workbook)
    workbook_snapshot.update(
        {
            "calculation_id": calculation.id,
            "calculation_title": calculation.title,
            "calculation_created_at": calculation.created_at.isoformat(),
            "calculation_status": calculation.status,
            "updated_at": calculation.updated_at.isoformat(),
        }
    )
    return InputWorkbook.model_validate(workbook_snapshot)


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


def calculation_read(calculation: Calculation, seed_workbook: InputWorkbook | None = None) -> CalculationRead:
    return CalculationRead(**calculation_summary(calculation).model_dump(), input=calculation_to_workbook(calculation, seed_workbook))


def write_workbook_json(workbook: InputWorkbook, path: Path, *, soil_curve_tables: list[dict[str, Any]] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(workbook_to_json(workbook, soil_curve_tables=soil_curve_tables), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

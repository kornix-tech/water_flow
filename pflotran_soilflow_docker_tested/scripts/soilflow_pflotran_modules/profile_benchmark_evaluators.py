from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from soilflow_pflotran_modules.test_registry import PFLOTRAN_PROFILE_TESTS
from soilflow_pflotran_modules.profile_benchmark_cases import profile_benchmark_case_status_fields


@dataclass(frozen=True)
class ProfileOverlayTolerance:
    theta_max_abs_m3_m3: float
    pressure_head_max_abs_m: float


DEFAULT_REFERENCE_OVERLAY_TOLERANCE = ProfileOverlayTolerance(
    theta_max_abs_m3_m3=0.35,
    pressure_head_max_abs_m=5.0,
)


def _metric_float(value: object) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def profile_evaluator_metadata(test_name: str) -> dict[str, object]:
    if test_name not in PFLOTRAN_PROFILE_TESTS:
        raise ValueError(f"Для теста {test_name} не зарегистрирован profile benchmark evaluator")
    return {
        "profile_evaluator": "reference_overlay",
        "strict_profile_evaluator_note": (
            "Profile benchmark пока проверяется как TECPLOT-ready reference overlay; "
            "строгий физический evaluator подключается отдельным case/evaluator модулем."
        ),
        **profile_benchmark_case_status_fields(test_name),
    }


def evaluate_reference_overlay_quality(
    metrics: dict[str, object],
    tolerance: ProfileOverlayTolerance = DEFAULT_REFERENCE_OVERLAY_TOLERANCE,
) -> dict[str, object]:
    if metrics.get("profile_overlay_comparison") != "REFERENCE_OVERLAY":
        return {
            "profile_overlay_quality_check": "SKIP",
            "profile_overlay_quality_note": "Reference overlay отсутствует или не содержит точек для сравнения.",
        }

    theta_max_abs = _metric_float(metrics.get("theta_overlay_max_abs_m3_m3"))
    pressure_head_max_abs = _metric_float(metrics.get("pressure_head_overlay_max_abs_m"))
    base: dict[str, object] = {
        "profile_overlay_theta_limit_m3_m3": f"{tolerance.theta_max_abs_m3_m3:.12g}",
        "profile_overlay_pressure_head_limit_m": f"{tolerance.pressure_head_max_abs_m:.12g}",
    }
    if theta_max_abs is None or pressure_head_max_abs is None:
        return {
            **base,
            "profile_overlay_quality_check": "UNKNOWN",
            "profile_overlay_quality_note": "Reference overlay записан, но численные max-error метрики не распознаны.",
        }

    passed = (
        theta_max_abs <= tolerance.theta_max_abs_m3_m3
        and pressure_head_max_abs <= tolerance.pressure_head_max_abs_m
    )
    return {
        **base,
        "profile_overlay_quality_check": "PASS" if passed else "WARN",
        "profile_overlay_quality_note": (
            "Диагностический reference overlay уложился в инженерные smoke-границы."
            if passed
            else "Диагностический reference overlay вышел за инженерные smoke-границы; это не strict FAIL."
        ),
    }

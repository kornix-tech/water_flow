from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class RichardsMmsStrictTolerance:
    theta_rmse_m3_m3: float = 0.02
    theta_max_abs_m3_m3: float = 0.05
    pressure_head_rmse_m: float = 0.05
    pressure_head_max_abs_m: float = 0.10


RICHARDS_MMS_STRICT_TOLERANCE = RichardsMmsStrictTolerance()


def _finite_metric(metrics: dict[str, object], key: str) -> float | None:
    value = metrics.get(key)
    if value in (None, ""):
        return None
    try:
        number = float(str(value))
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def evaluate_richards_mms_strict_candidate(
    metrics: dict[str, object],
    tolerance: RichardsMmsStrictTolerance = RICHARDS_MMS_STRICT_TOLERANCE,
) -> dict[str, object]:
    base: dict[str, object] = {
        "richards_mms_strict_evaluator": "READY_DECK_PENDING",
        "richards_mms_theta_rmse_limit_m3_m3": f"{tolerance.theta_rmse_m3_m3:.12g}",
        "richards_mms_theta_max_abs_limit_m3_m3": f"{tolerance.theta_max_abs_m3_m3:.12g}",
        "richards_mms_pressure_head_rmse_limit_m": f"{tolerance.pressure_head_rmse_m:.12g}",
        "richards_mms_pressure_head_max_abs_limit_m": f"{tolerance.pressure_head_max_abs_m:.12g}",
    }
    if metrics.get("profile_overlay_comparison") != "REFERENCE_OVERLAY":
        return {
            **base,
            "richards_mms_strict_candidate_check": "SKIP",
            "richards_mms_strict_candidate_note": "Нет reference overlay для strict-кандидата Richards MMS.",
        }

    theta_rmse = _finite_metric(metrics, "theta_overlay_rmse_m3_m3")
    theta_max_abs = _finite_metric(metrics, "theta_overlay_max_abs_m3_m3")
    pressure_rmse = _finite_metric(metrics, "pressure_head_overlay_rmse_m")
    pressure_max_abs = _finite_metric(metrics, "pressure_head_overlay_max_abs_m")
    if None in (theta_rmse, theta_max_abs, pressure_rmse, pressure_max_abs):
        return {
            **base,
            "richards_mms_strict_candidate_check": "UNKNOWN",
            "richards_mms_strict_candidate_note": "Reference overlay есть, но strict-кандидат не распознал все метрики.",
        }

    passed = (
        theta_rmse <= tolerance.theta_rmse_m3_m3
        and theta_max_abs <= tolerance.theta_max_abs_m3_m3
        and pressure_rmse <= tolerance.pressure_head_rmse_m
        and pressure_max_abs <= tolerance.pressure_head_max_abs_m
    )
    return {
        **base,
        "richards_mms_strict_candidate_check": "PASS" if passed else "FAIL",
        "richards_mms_strict_candidate_note": (
            "Strict-кандидат Richards MMS прошел по profile overlay; для повышения уровня нужен MMS deck/source-term."
            if passed
            else "Strict-кандидат Richards MMS не прошел по profile overlay; это диагностический результат до замены carrier deck."
        ),
    }

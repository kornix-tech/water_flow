from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProfilePoint:
    coordinate_m: float
    pressure_pa: float | None = None
    saturation: float | None = None
    water_content_m3_m3: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SolverDiagnostics:
    error_count: int = 0
    warning_count: int = 0
    diverged: bool = False
    timestep_cuts: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CalculationResultContract:
    profiles: list[ProfilePoint]
    diagnostics: SolverDiagnostics
    status: str
    source_solver: str
    raw_files: list[str] = field(default_factory=list)


def profile_rows_to_contract(rows: list[dict[str, float]], source_solver: str = "pflotran") -> CalculationResultContract:
    profiles = [
        ProfilePoint(
            coordinate_m=float(row["z_m"]),
            pressure_pa=float(row["pressure_pa"]) if "pressure_pa" in row else None,
            saturation=float(row["saturation"]) if "saturation" in row else None,
        )
        for row in rows
    ]
    return CalculationResultContract(
        profiles=profiles,
        diagnostics=SolverDiagnostics(),
        status="PARSED",
        source_solver=source_solver,
    )

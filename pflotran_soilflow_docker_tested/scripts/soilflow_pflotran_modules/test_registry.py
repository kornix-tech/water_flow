from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class TestDefinition:
    name: str
    output_dir: str
    group: str
    requires_richards_runner: bool
    verification_level: str


TEST_OUTPUT_DIRS = {
    "linear_darcy": "_test_linear_darcy",
    "hydrostatic_vg_no_flow": "_test_hydrostatic_vg_no_flow",
    "unit_gradient_unsat": "_test_unit_gradient_unsat",
    "transient_uniform_storage_vg": "_test_transient_uniform_storage_vg",
    "brooks_corey_burdine": "_test_brooks_corey_burdine",
    "theis_radial_flow": "_test_theis_radial_flow",
    "ogata_banks_1d_transport": "_test_ogata_banks_1d_transport",
    "terzaghi_1d_consolidation": "_test_terzaghi_1d_consolidation",
    "philip_infiltration": "_test_philip_infiltration",
    "green_ampt_infiltration": "_test_green_ampt_infiltration",
    "heat_conduction_1d": "_test_heat_conduction_1d",
    "buckley_leverett": "_test_buckley_leverett",
    "richards_mms": "_test_richards_mms",
    "boussinesq_groundwater_mound": "_test_boussinesq_groundwater_mound",
}

PFLOTRAN_RICHARDS_TESTS = {
    "linear_darcy",
    "hydrostatic_vg_no_flow",
    "unit_gradient_unsat",
    "transient_uniform_storage_vg",
    "brooks_corey_burdine",
}

PFLOTRAN_PROFILE_TESTS = {
    "theis_radial_flow",
    "ogata_banks_1d_transport",
    "terzaghi_1d_consolidation",
    "philip_infiltration",
    "green_ampt_infiltration",
    "heat_conduction_1d",
    "buckley_leverett",
    "richards_mms",
    "boussinesq_groundwater_mound",
}

STRICT_ANALYTICAL_TESTS = {
    "linear_darcy",
    "hydrostatic_vg_no_flow",
    "unit_gradient_unsat",
    "brooks_corey_burdine",
}
PARTIAL_BALANCE_TESTS = {"transient_uniform_storage_vg"}
PROFILE_SMOKE_TESTS = set(PFLOTRAN_PROFILE_TESTS)

TEST_REGISTRY = tuple(TEST_OUTPUT_DIRS)


def verification_level_for_test(test_name: str) -> str:
    if test_name in STRICT_ANALYTICAL_TESTS:
        return "strict_analytical"
    if test_name in PARTIAL_BALANCE_TESTS:
        return "partial_balance"
    if test_name in PROFILE_SMOKE_TESTS:
        return "profile_smoke"
    return "generated_only"


TEST_DEFINITIONS: tuple[TestDefinition, ...] = tuple(
    TestDefinition(
        name=name,
        output_dir=output_dir,
        group="richards_verification" if name in PFLOTRAN_RICHARDS_TESTS else "profile_benchmark",
        requires_richards_runner=name in PFLOTRAN_RICHARDS_TESTS,
        verification_level=verification_level_for_test(name),
    )
    for name, output_dir in TEST_OUTPUT_DIRS.items()
)


def selected_test_names(test_name: str) -> list[str]:
    return list(TEST_REGISTRY) if test_name == "all" else [test_name]


def test_params_from_document(data: dict[str, Any], test_name: str = "linear_darcy") -> dict[str, Any]:
    scenarios = data.get("test_scenarios", {})
    params = scenarios.get(test_name, {}) if isinstance(scenarios, dict) else {}
    if not params:
        raise ValueError(f"В JSON отсутствует сценарий теста {test_name!r}")
    return params


def test_workdir_for(
    *,
    test_name: str,
    output_dir: Path | None,
    workdir: Path | None,
    selected_test: str,
) -> Path:
    if workdir is not None and selected_test != "all":
        return workdir
    if output_dir is None:
        return Path("runs") / TEST_OUTPUT_DIRS[test_name]
    return output_dir / "runs" / TEST_OUTPUT_DIRS[test_name]


def suite_workdir_for(output_dir: Path | None) -> Path:
    return output_dir / "runs" / "_test_suite" if output_dir is not None else Path("runs/_test_suite")

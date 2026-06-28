from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from soilflow_pflotran_modules.input_contract import pf_float


@dataclass(frozen=True)
class ProfileCaseBuilderSpec:
    test_name: str
    builder_status: str
    physics_adapter: str
    candidate_input_name: str
    parser_contract: str
    evaluator_contract: str
    note: str


CASE_BUILDER_SPECS: dict[str, ProfileCaseBuilderSpec] = {
    "heat_conduction_1d": ProfileCaseBuilderSpec(
        test_name="heat_conduction_1d",
        builder_status="CASE_BUILDER_CANDIDATE_READY",
        physics_adapter="thermal_1d_conduction",
        candidate_input_name="pflotran_heat_conduction_candidate.in",
        parser_contract="temperature_profile_x_t",
        evaluator_contract="T(x,t) erfc semi-infinite conduction",
        note="Кандидат постановки фиксирует расчетную область, тепловые параметры и Dirichlet-step boundary для будущего thermal parser/evaluator.",
    ),
    "ogata_banks_1d_transport": ProfileCaseBuilderSpec(
        test_name="ogata_banks_1d_transport",
        builder_status="CASE_BUILDER_CANDIDATE_READY",
        physics_adapter="transport_1d_advection_dispersion",
        candidate_input_name="pflotran_ogata_banks_candidate.in",
        parser_contract="concentration_profile_x_t",
        evaluator_contract="C(x,t) Ogata-Banks advection-dispersion",
        note="Кандидат постановки отделяет transport deck от Richards profile carrier; strict gate ждет concentration parser/evaluator.",
    ),
    "theis_radial_flow": ProfileCaseBuilderSpec(
        test_name="theis_radial_flow",
        builder_status="CASE_BUILDER_CANDIDATE_READY",
        physics_adapter="groundwater_radial_drawdown",
        candidate_input_name="pflotran_theis_radial_candidate.in",
        parser_contract="drawdown_radius_t",
        evaluator_contract="s(r,t) Theis well-function",
        note="Кандидат постановки задает radial drawdown contract; strict gate ждет groundwater parser и mapping PFLOTRAN output к радиусам.",
    ),
    "boussinesq_groundwater_mound": ProfileCaseBuilderSpec(
        test_name="boussinesq_groundwater_mound",
        builder_status="CASE_BUILDER_CANDIDATE_READY",
        physics_adapter="groundwater_unconfined_mound",
        candidate_input_name="pflotran_boussinesq_mound_candidate.in",
        parser_contract="water_table_head_x_t",
        evaluator_contract="h(x,t) linearized Boussinesq mound decay",
        note="Кандидат постановки фиксирует unconfined-head contract; strict gate ждет solver adapter для water-table/head output.",
    ),
}


def profile_case_builder_spec(test_name: str) -> ProfileCaseBuilderSpec | None:
    return CASE_BUILDER_SPECS.get(test_name)


def profile_case_builder_status(test_name: str) -> str:
    spec = profile_case_builder_spec(test_name)
    return spec.builder_status if spec else "CASE_BUILDER_PENDING"


def profile_case_builder_manifest(test_name: str) -> dict[str, object]:
    spec = profile_case_builder_spec(test_name)
    if spec is None:
        return {
            "schema_version": 1,
            "test_name": test_name,
            "builder_status": "CASE_BUILDER_PENDING",
            "candidate_input": None,
            "parser_contract": None,
            "evaluator_contract": None,
        }
    return {
        "schema_version": 1,
        "test_name": spec.test_name,
        "builder_status": spec.builder_status,
        "physics_adapter": spec.physics_adapter,
        "candidate_input": spec.candidate_input_name,
        "parser_contract": spec.parser_contract,
        "evaluator_contract": spec.evaluator_contract,
        "note": spec.note,
    }


def write_profile_case_builder_artifacts(test_name: str, workdir: Path) -> list[Path]:
    spec = profile_case_builder_spec(test_name)
    if spec is None:
        return []
    manifest_path = workdir / "profile_case_builder_manifest.json"
    candidate_path = workdir / spec.candidate_input_name
    manifest_path.write_text(
        json.dumps(profile_case_builder_manifest(test_name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    candidate_path.write_text(generate_profile_case_builder_candidate_input(spec), encoding="utf-8")
    return [manifest_path, candidate_path]


def generate_profile_case_builder_candidate_input(spec: ProfileCaseBuilderSpec) -> str:
    if spec.test_name == "heat_conduction_1d":
        return _heat_conduction_candidate(spec)
    if spec.test_name == "ogata_banks_1d_transport":
        return _ogata_banks_candidate(spec)
    if spec.test_name == "theis_radial_flow":
        return _theis_radial_candidate(spec)
    if spec.test_name == "boussinesq_groundwater_mound":
        return _boussinesq_mound_candidate(spec)
    raise ValueError(f"Для profile benchmark {spec.test_name} нет case-builder candidate")


def _candidate_header(spec: ProfileCaseBuilderSpec) -> list[str]:
    return [
        f"# Candidate case-builder artifact for {spec.test_name}",
        f"# builder_status={spec.builder_status}",
        f"# physics_adapter={spec.physics_adapter}",
        f"# parser_contract={spec.parser_contract}",
        f"# evaluator_contract={spec.evaluator_contract}",
        "# Этот файл пока не является strict gate deck: он фиксирует постановку",
        "# и контракт будущего parser/evaluator без подмены текущего profile carrier.",
        "",
    ]


def _structured_grid_block(nx: int, ny: int, nz: int, lx: float, ly: float, lz: float) -> list[str]:
    return [
        "GRID",
        "  TYPE structured",
        "  ORIGIN 0.d0 0.d0 0.d0",
        f"  NXYZ {nx} {ny} {nz}",
        "  DXYZ",
        f"    {pf_float(lx / nx)}",
        f"    {pf_float(ly / ny)}",
        f"    {pf_float(lz / nz)}",
        "  /",
        "END",
        "",
    ]


def _heat_conduction_candidate(spec: ProfileCaseBuilderSpec) -> str:
    lines = [
        *_candidate_header(spec),
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_ENERGY energy",
        "      MODE TH",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        *_structured_grid_block(100, 1, 1, 2.0, 1.0, 1.0),
        "# target: T(x,t)=Ti+(Ts-Ti)*erfc(x/(2*sqrt(kappa*t)))",
        f"# thermal_diffusivity_m2_s={pf_float(1.0e-6)}",
        f"# initial_temperature_c={pf_float(10.0)}",
        f"# surface_temperature_c={pf_float(20.0)}",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def _ogata_banks_candidate(spec: ProfileCaseBuilderSpec) -> str:
    lines = [
        *_candidate_header(spec),
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_TRANSPORT transport",
        "      MODE GIRT",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        *_structured_grid_block(100, 1, 1, 20.0, 1.0, 1.0),
        "# target: Ogata-Banks C(x,t) for constant inlet concentration",
        f"# pore_velocity_m_s={pf_float(1.0)}",
        f"# dispersion_m2_s={pf_float(0.1)}",
        f"# inlet_concentration={pf_float(1.0)}",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def _theis_radial_candidate(spec: ProfileCaseBuilderSpec) -> str:
    lines = [
        *_candidate_header(spec),
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_FLOW flow",
        "      MODE RICHARDS",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        *_structured_grid_block(128, 1, 1, 250.0, 1.0, 1.0),
        "# target: Theis drawdown s(r,t)=Q/(4*pi*T)*W(u)",
        f"# transmissivity_m2_s={pf_float(1.0e-3)}",
        f"# storage_coefficient={pf_float(1.0e-4)}",
        f"# pumping_rate_m3_s={pf_float(1.0e-3)}",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)


def _boussinesq_mound_candidate(spec: ProfileCaseBuilderSpec) -> str:
    lines = [
        *_candidate_header(spec),
        "SIMULATION",
        "  SIMULATION_TYPE SUBSURFACE",
        "  PROCESS_MODELS",
        "    SUBSURFACE_FLOW flow",
        "      MODE RICHARDS",
        "    /",
        "  /",
        "END",
        "",
        "SUBSURFACE",
        "",
        *_structured_grid_block(100, 1, 1, 100.0, 1.0, 1.0),
        "# target: linearized Boussinesq groundwater mound h(x,t)",
        f"# base_head_m={pf_float(10.0)}",
        f"# mound_amplitude_m={pf_float(1.0)}",
        f"# hydraulic_diffusivity_m2_day={pf_float(20.0)}",
        "END_SUBSURFACE",
        "",
    ]
    return "\n".join(lines)

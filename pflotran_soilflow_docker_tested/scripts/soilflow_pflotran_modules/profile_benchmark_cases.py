from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProfileBenchmarkCase:
    name: str
    physics_family: str
    carrier_status: str
    strict_evaluator_status: str
    case_builder_status: str
    deck_kind: str
    strict_candidate_can_gate_suite: bool
    strict_blocker: str
    next_step: str


PROFILE_BENCHMARK_CASES: dict[str, ProfileBenchmarkCase] = {
    "richards_mms": ProfileBenchmarkCase(
        name="richards_mms",
        physics_family="richards",
        carrier_status="MMS_SPATIAL_ADAPTER_READY",
        strict_evaluator_status="STRICT_CANDIDATE_READY",
        case_builder_status="CASE_BUILDER_READY",
        deck_kind="richards_mms_spatial_source_candidate",
        strict_candidate_can_gate_suite=True,
        strict_blocker="Spatial MMS adapter deck подключен; следующий риск - подтвердить устойчивость на расширенных сетках и tolerances.",
        next_step="Расширить solver validation Richards MMS на несколько сеток/шагов и затем перевести его из profile_smoke в strict_analytical уровень.",
    ),
    "philip_infiltration": ProfileBenchmarkCase(
        name="philip_infiltration",
        physics_family="richards_infiltration",
        carrier_status="PROFILE_CARRIER_READY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_READY",
        deck_kind="richards_profile_carrier",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Текущий reference overlay использует wetting-front профиль, а не строгий Richards/Philip field solution.",
        next_step="Выделить infiltration case-builder и evaluator по фронту/накопленной инфильтрации.",
    ),
    "green_ampt_infiltration": ProfileBenchmarkCase(
        name="green_ampt_infiltration",
        physics_family="richards_infiltration",
        carrier_status="PROFILE_CARRIER_READY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_READY",
        deck_kind="richards_profile_carrier",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Нужна явная метрика положения фронта и cumulative infiltration из PFLOTRAN mass balance.",
        next_step="Подключить evaluator Green-Ampt по фронту, накопленной инфильтрации и mass balance.",
    ),
    "theis_radial_flow": ProfileBenchmarkCase(
        name="theis_radial_flow",
        physics_family="groundwater_radial",
        carrier_status="CASE_BUILDER_CANDIDATE_READY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_CANDIDATE_READY",
        deck_kind="groundwater_radial_drawdown_candidate",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Case-builder candidate есть; strict gate ждет groundwater parser/evaluator drawdown(r,t) и solver adapter.",
        next_step="Подключить parser drawdown(r,t), сверить Theis well-function и только затем включать strict_candidate_can_gate_suite.",
    ),
    "ogata_banks_1d_transport": ProfileBenchmarkCase(
        name="ogata_banks_1d_transport",
        physics_family="transport",
        carrier_status="CASE_BUILDER_CANDIDATE_READY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_CANDIDATE_READY",
        deck_kind="transport_1d_advection_dispersion_candidate",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Case-builder candidate есть; strict gate ждет concentration parser/evaluator C(x,t).",
        next_step="Подключить parser концентрационного output и evaluator Ogata-Banks C(x,t).",
    ),
    "terzaghi_1d_consolidation": ProfileBenchmarkCase(
        name="terzaghi_1d_consolidation",
        physics_family="poroelastic_consolidation",
        carrier_status="REFERENCE_ONLY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_PENDING",
        deck_kind="reference_only",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Текущий solver path не содержит poroelastic consolidation постановку.",
        next_step="Добавить consolidation case-builder или отделить как external reference до появления solver support.",
    ),
    "heat_conduction_1d": ProfileBenchmarkCase(
        name="heat_conduction_1d",
        physics_family="heat",
        carrier_status="CASE_BUILDER_CANDIDATE_READY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_CANDIDATE_READY",
        deck_kind="thermal_1d_conduction_candidate",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Case-builder candidate есть; strict gate ждет temperature parser/evaluator T(x,t).",
        next_step="Подключить parser температурного output и evaluator erfc T(x,t).",
    ),
    "buckley_leverett": ProfileBenchmarkCase(
        name="buckley_leverett",
        physics_family="two_phase",
        carrier_status="REFERENCE_ONLY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_PENDING",
        deck_kind="reference_only",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Нужен two-phase deck и parser saturation/front output.",
        next_step="Добавить two-phase displacement case-builder и evaluator fractional-flow/front position.",
    ),
    "boussinesq_groundwater_mound": ProfileBenchmarkCase(
        name="boussinesq_groundwater_mound",
        physics_family="groundwater_unconfined",
        carrier_status="CASE_BUILDER_CANDIDATE_READY",
        strict_evaluator_status="PENDING",
        case_builder_status="CASE_BUILDER_CANDIDATE_READY",
        deck_kind="groundwater_unconfined_mound_candidate",
        strict_candidate_can_gate_suite=False,
        strict_blocker="Case-builder candidate есть; strict gate ждет water-table/head parser/evaluator h(x,t).",
        next_step="Подключить parser head(x,t) и evaluator Boussinesq mound decay.",
    ),
}


def profile_benchmark_case(test_name: str) -> ProfileBenchmarkCase:
    try:
        return PROFILE_BENCHMARK_CASES[test_name]
    except KeyError as exc:
        raise ValueError(f"Для profile benchmark {test_name} нет case metadata") from exc


def profile_benchmark_case_status_fields(test_name: str) -> dict[str, object]:
    case = profile_benchmark_case(test_name)
    strict_plan = profile_benchmark_strict_plan(test_name)
    return {
        "profile_physics_family": case.physics_family,
        "profile_carrier_status": case.carrier_status,
        "profile_case_builder_status": case.case_builder_status,
        "profile_deck_kind": case.deck_kind,
        "strict_profile_evaluator": case.strict_evaluator_status,
        "strict_candidate_can_gate_suite": case.strict_candidate_can_gate_suite,
        "strict_profile_evaluator_blocker": case.strict_blocker,
        "strict_profile_evaluator_next_step": case.next_step,
        "strict_readiness_stage": strict_plan["strict_readiness_stage"],
    }


def profile_benchmark_strict_plan(test_name: str) -> dict[str, object]:
    case = profile_benchmark_case(test_name)
    if case.strict_candidate_can_gate_suite:
        readiness_stage = "STRICT_GATE_READY"
    elif case.strict_evaluator_status == "EVALUATOR_READY_DECK_PENDING":
        readiness_stage = "DECK_ADAPTER_PENDING"
    elif case.case_builder_status == "CASE_BUILDER_PENDING":
        readiness_stage = "CASE_BUILDER_PENDING"
    else:
        readiness_stage = "STRICT_EVALUATOR_PENDING"
    return {
        "schema_version": 1,
        "test_name": case.name,
        "profile_physics_family": case.physics_family,
        "profile_carrier_status": case.carrier_status,
        "profile_case_builder_status": case.case_builder_status,
        "profile_deck_kind": case.deck_kind,
        "strict_profile_evaluator": case.strict_evaluator_status,
        "strict_candidate_can_gate_suite": case.strict_candidate_can_gate_suite,
        "strict_readiness_stage": readiness_stage,
        "strict_profile_evaluator_blocker": case.strict_blocker,
        "strict_profile_evaluator_next_step": case.next_step,
    }


def profile_benchmark_case_manifest(test_name: str) -> dict[str, object]:
    case = profile_benchmark_case(test_name)
    strict_plan = profile_benchmark_strict_plan(test_name)
    return {
        "schema_version": 1,
        "test_name": case.name,
        "profile_physics_family": case.physics_family,
        "profile_carrier_status": case.carrier_status,
        "profile_case_builder_status": case.case_builder_status,
        "profile_deck_kind": case.deck_kind,
        "strict_profile_evaluator": case.strict_evaluator_status,
        "strict_candidate_can_gate_suite": case.strict_candidate_can_gate_suite,
        "strict_profile_evaluator_blocker": case.strict_blocker,
        "strict_profile_evaluator_next_step": case.next_step,
        "strict_readiness_stage": strict_plan["strict_readiness_stage"],
    }


def write_profile_benchmark_case_manifest(test_name: str, workdir: Path) -> Path:
    manifest_path = workdir / "profile_case_manifest.json"
    manifest_path.write_text(
        json.dumps(profile_benchmark_case_manifest(test_name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def write_profile_benchmark_strict_plan(test_name: str, workdir: Path) -> Path:
    plan_path = workdir / "profile_strict_plan.json"
    plan_path.write_text(
        json.dumps(profile_benchmark_strict_plan(test_name), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return plan_path

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from soilflow_pflotran_modules.contracts import MODULE_BOUNDARIES, REPLACEABLE_ADAPTERS
from soilflow_pflotran_modules.demo_deck_writer import build_demo_grid, generate_standard_pflotran_input
from soilflow_pflotran_modules.extended_analytical import (
    buckley_fractional_flow,
    generate_extended_analytical_rows,
    generate_normalized_profile_rows,
    green_ampt_cumulative_infiltration,
)
from soilflow_pflotran_modules.input_contract import as_bool, as_float, as_int, optional_float, pf_float
from soilflow_pflotran_modules.physical_models import (
    model_pair_label,
    normalize_grid_dimension,
    normalize_model_token,
    pressure_head_from_vg_saturation,
    saturation_from_effective_saturation,
    validate_soil_model_pair,
    vg_effective_saturation_from_pressure_head,
    vg_mualem_relative_permeability,
)
from soilflow_pflotran_modules.profile_benchmarks import (
    profile_overlay_error_metrics,
    profile_status_fields_after_run,
    write_profile_overlay_comparison,
    write_richards_profile_analytical_profiles,
)
from soilflow_pflotran_modules.profile_benchmark_evaluators import evaluate_reference_overlay_quality
from soilflow_pflotran_modules.profile_benchmark_cases import (
    profile_benchmark_case_status_fields,
    write_profile_benchmark_case_manifest,
)
from soilflow_pflotran_modules.profile_carrier import generate_richards_profile_input
from soilflow_pflotran_modules.profile_strict_evaluators import evaluate_richards_mms_strict_candidate
from soilflow_pflotran_modules.profile_test_runner import generate_profile_test_files
from soilflow_pflotran_modules.result_contract import profile_rows_to_contract
from soilflow_pflotran_modules.result_diagnostics import (
    classify_pflotran_warnings,
    direct_flux_output_probe,
    fit_line_slope,
    load_tecpotran_records,
    parse_pflotran_solver_diagnostics,
    parse_tecpotran_tec,
    records_to_z_pressure_saturation,
    write_unified_status,
)
from soilflow_pflotran_modules.richards_test_cases import (
    TEST_BUILDERS,
    build_linear_darcy_test,
    build_transient_uniform_storage_vg_test,
    generate_pflotran_test_input,
    transient_rate_m3_day,
    write_analytical_solution,
)
from soilflow_pflotran_modules.richards_test_evaluators import write_test_comparison, write_test_svg
from soilflow_pflotran_modules.richards_test_runner import generate_richards_test_files
from soilflow_pflotran_modules.solver_runner import find_pflotran_native, run_native
from soilflow_pflotran_modules.surface_balance import (
    SimpleSurfaceFluxModel,
    compute_mean_top_flux_m_s,
    normalize_weather_row,
    write_weather_csv,
)
from soilflow_pflotran_modules.tabular_curves import build_tabular_characteristic_curve_assets, build_tabular_permeability_assets
from soilflow_pflotran_modules.test_artifacts import (
    analytical_profile_overlay_diagnostics,
    write_curve_svg,
    write_rows_csv,
)
from soilflow_pflotran_modules.test_evaluation import combined_test_status, suite_status_lines, write_suite_status_file
from soilflow_pflotran_modules.test_registry import (
    TEST_REGISTRY,
    selected_test_names,
    suite_workdir_for,
    test_params_from_document,
    test_workdir_for,
    verification_level_for_test,
)
from soilflow_pflotran_modules.test_solver_execution import execute_test_solver
from soilflow_pflotran_modules.verification_runner import (
    resolve_test_workdir,
    run_test_mode as run_verification_test_mode,
)
from soilflow_pflotran import compute_derived, generate_pflotran_input, read_params, read_weather, run_demo_mode


class InputContractTests(unittest.TestCase):
    def test_number_parsing_accepts_russian_decimal_comma(self) -> None:
        self.assertEqual(as_float("1,25"), 1.25)
        self.assertEqual(as_int("4.0"), 4)
        self.assertIsNone(optional_float(""))

    def test_bool_parsing_accepts_russian_truthy_values(self) -> None:
        self.assertTrue(as_bool("да"))
        self.assertTrue(as_bool("вкл"))
        self.assertFalse(as_bool(""))

    def test_pf_float_uses_fortran_d_exponent(self) -> None:
        self.assertEqual(pf_float(0.0), "0.d0")
        self.assertIn("d", pf_float(1.0e-6))


class ArchitectureContractTests(unittest.TestCase):
    def test_replaceable_adapter_boundaries_are_declared(self) -> None:
        adapter_names = {adapter.name for adapter in REPLACEABLE_ADAPTERS}

        self.assertTrue({"solver", "surface_balance", "result_parser"}.issubset(adapter_names))
        self.assertIn("solver_runner", MODULE_BOUNDARIES)
        self.assertIn("surface_balance", MODULE_BOUNDARIES)
        self.assertIn("result_diagnostics", MODULE_BOUNDARIES)
        self.assertIn("result_contract", MODULE_BOUNDARIES)
        self.assertIn("test_evaluation", MODULE_BOUNDARIES)
        self.assertIn("test_suite_artifacts", MODULE_BOUNDARIES)
        self.assertIn("profile_benchmarks", MODULE_BOUNDARIES)
        self.assertIn("profile_benchmark_cases", MODULE_BOUNDARIES)
        self.assertIn("profile_benchmark_evaluators", MODULE_BOUNDARIES)
        self.assertIn("richards_test_cases", MODULE_BOUNDARIES)
        self.assertIn("richards_test_evaluators", MODULE_BOUNDARIES)
        self.assertIn("richards_test_runner", MODULE_BOUNDARIES)
        self.assertIn("profile_test_runner", MODULE_BOUNDARIES)
        self.assertIn("test_solver_execution", MODULE_BOUNDARIES)
        self.assertIn("verification_runner", MODULE_BOUNDARIES)


class PhysicalModelTests(unittest.TestCase):
    def test_model_tokens_and_grid_dimension_are_normalized(self) -> None:
        self.assertEqual(normalize_model_token("Brooks-Corey", "van_genuchten"), "brooks_corey")
        self.assertEqual(normalize_grid_dimension("2", "XY"), "2d_xy")
        self.assertEqual(normalize_grid_dimension("2", "XZ"), "2d_xz")

    def test_supported_soil_model_pair_is_accepted(self) -> None:
        validate_soil_model_pair("brooks_corey", "burdine")
        self.assertEqual(model_pair_label("brooks_corey", "burdine"), "Brooks-Corey + Burdine")

    def test_unsupported_soil_model_pair_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_soil_model_pair("gardner", "mualem")

    def test_tabular_pair_is_accepted(self) -> None:
        validate_soil_model_pair("van_genuchten", "tabular")
        self.assertEqual(model_pair_label("van_genuchten", "tabular"), "van Genuchten + Табличная кривая")
        validate_soil_model_pair("tabular", "tabular")

    def test_van_genuchten_helpers_are_bounded_and_invertible(self) -> None:
        residual_saturation = 0.1
        alpha_1_m = 3.6
        n = 1.56
        m = 1.0 - 1.0 / n

        effective_saturation = vg_effective_saturation_from_pressure_head(-0.8, alpha_1_m, n, m)
        saturation = saturation_from_effective_saturation(effective_saturation, residual_saturation)
        pressure_head = pressure_head_from_vg_saturation(saturation, residual_saturation, alpha_1_m, n, m)
        relative_permeability = vg_mualem_relative_permeability(effective_saturation, m)

        self.assertGreater(effective_saturation, 0.0)
        self.assertLessEqual(effective_saturation, 1.0)
        self.assertAlmostEqual(pressure_head, -0.8, places=9)
        self.assertGreaterEqual(relative_permeability, 0.0)
        self.assertLessEqual(relative_permeability, 1.0)


class RichardsTestCaseModuleTests(unittest.TestCase):
    def test_strict_test_builders_and_darcy_artifacts_are_independent_module_contract(self) -> None:
        self.assertIn("linear_darcy", TEST_BUILDERS)
        test = build_linear_darcy_test({"column_height_m": 2.0, "bottom_pressure_pa": 125000.0})
        deck = generate_pflotran_test_input(test)

        self.assertIn("MODE RICHARDS", deck)
        self.assertIn("LIQUID_FLUX", deck)

        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            analytical_path = workdir / "analytical_solution.csv"
            comparison_path = workdir / "test_comparison.csv"
            svg_path = workdir / "test_comparison.svg"

            write_analytical_solution(test, analytical_path)
            max_abs, max_rel, points = write_test_comparison(
                test,
                [(0.5, test.bottom_pressure_pa - test.rho_water_kg_m3 * test.gravity_m_s2 * (1.0 + test.imposed_flux_z_m_s / test.ksat_m_s) * 0.5)],
                comparison_path,
            )
            write_test_svg(test, comparison_path, svg_path)

            self.assertEqual(points, 1)
            self.assertEqual(max_abs, 0.0)
            self.assertEqual(max_rel, 0.0)
            self.assertIn("pressure_analytical_pa", analytical_path.read_text(encoding="utf-8"))
            self.assertIn("<svg", svg_path.read_text(encoding="utf-8"))

    def test_transient_storage_builder_exposes_partial_balance_rate_contract(self) -> None:
        test = build_transient_uniform_storage_vg_test({})

        self.assertIn("transient_uniform_storage_vg", TEST_BUILDERS)
        self.assertGreater(transient_rate_m3_day(test, test.period_days / 4.0), 0.0)
        self.assertAlmostEqual(transient_rate_m3_day(test, 0.0), 0.0, places=12)


class VerificationRunnerModuleTests(unittest.TestCase):
    def test_single_test_generation_is_runner_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            args = SimpleNamespace(output_dir=None, workdir=workdir, test="linear_darcy")

            self.assertEqual(resolve_test_workdir(args, "linear_darcy"), workdir)
            generated = generate_richards_test_files("linear_darcy", {}, workdir)

            self.assertEqual(generated.test_case_id, "linear_darcy_saturated_column")
            self.assertTrue((workdir / "pflotran.in").exists())
            self.assertTrue((workdir / "analytical_solution.csv").exists())
            self.assertTrue((workdir / "analytical_test_summary.txt").exists())

    def test_profile_generation_is_runner_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)

            generate_profile_test_files("theis_radial_flow", workdir)

            self.assertTrue((workdir / "pflotran.in").exists())
            self.assertTrue((workdir / "analytical_solution.csv").exists())
            self.assertTrue((workdir / "analytical_solution.svg").exists())
            self.assertTrue((workdir / "analytical_profiles.csv").exists())
            self.assertTrue((workdir / "analytical_test_summary.txt").exists())
            manifest = json.loads((workdir / "profile_case_manifest.json").read_text(encoding="utf-8"))
            summary = (workdir / "analytical_test_summary.txt").read_text(encoding="utf-8")
            self.assertEqual(manifest["profile_deck_kind"], "reference_only")
            self.assertFalse(manifest["strict_candidate_can_gate_suite"])
            self.assertIn("strict_candidate_can_gate_suite=false", summary)

    def test_dry_run_mode_writes_suite_status_without_solver(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_json = root / "input.json"
            output_dir = root / "out"
            input_json.write_text(
                '{"test_scenarios": {"linear_darcy": {"column_height_m": 2.0}}}',
                encoding="utf-8",
            )
            args = SimpleNamespace(
                input_json=input_json,
                output_dir=output_dir,
                workdir=None,
                test="linear_darcy",
                dry_run=True,
                run=False,
                pflotran_exe=None,
                prefer_wsl=False,
            )

            self.assertEqual(run_verification_test_mode(args), 0)

            status_path = output_dir / "runs" / "_test_suite" / "TEST_SUITE_STATUS.txt"
            status_text = status_path.read_text(encoding="utf-8")
            self.assertIn("TEST_SUITE_STATUS=DRY_RUN", status_text)
            self.assertIn("_test_linear_darcy=GENERATED", status_text)
            self.assertIn("strict_analytical_total=1", status_text)


class ExtendedAnalyticalTests(unittest.TestCase):
    def test_green_ampt_solution_is_monotonic(self) -> None:
        early = green_ampt_cumulative_infiltration(3600.0, 1.0e-6, 0.25, 0.25)
        late = green_ampt_cumulative_infiltration(7200.0, 1.0e-6, 0.25, 0.25)
        self.assertGreater(late, early)

    def test_buckley_fractional_flow_is_bounded(self) -> None:
        flow = buckley_fractional_flow(0.5, 0.2, 0.2, 1.0, 5.0)
        self.assertGreaterEqual(flow, 0.0)
        self.assertLessEqual(flow, 1.0)

    def test_extended_rows_and_normalized_profile_are_generated(self) -> None:
        rows, x_key, y_key, title, note = generate_extended_analytical_rows("theis_radial_flow")
        profile_rows = generate_normalized_profile_rows("theis_radial_flow", length_m=1.2)

        self.assertEqual(len(rows), 100)
        self.assertEqual(x_key, "radius_m")
        self.assertEqual(y_key, "drawdown_m")
        self.assertIn("Theis", title)
        self.assertIn("Theis", note)
        self.assertEqual(len(profile_rows), 100)
        self.assertTrue({"depth_m", "theta_m3_m3", "pressure_head_m"}.issubset(profile_rows[0]))

    def test_profile_carrier_generates_richards_tecpot_deck(self) -> None:
        deck = generate_richards_profile_input("theis_radial_flow")
        self.assertIn("PROCESS_MODELS", deck)
        self.assertIn("MODE RICHARDS", deck)
        self.assertIn("FORMAT TECPLOT POINT", deck)
        self.assertIn("CHARACTERISTIC_CURVES cc_vg", deck)

    def test_tabular_curves_generate_pchip_permeability_file(self) -> None:
        tables = [
            {
                "curve_name": "lab_conductivity",
                "curve_kind": "conductivity",
                "points": [
                    {"saturation": 0.2, "relative_permeability": 0.0},
                    {"saturation": 0.6, "relative_permeability": 0.25},
                    {"saturation": 1.0, "relative_permeability": 1.0},
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            assets = build_tabular_permeability_assets(
                tables=tables,
                workdir=Path(tmpdir),
                theta_s=0.45,
                ksat_m_s=1.0e-5,
            )
            deck = "\n".join(assets.permeability_function_lines)
            self.assertIn("PERMEABILITY_FUNCTION PCHIP_LIQ", deck)
            self.assertEqual(len(assets.written_files), 1)
            for written_file in assets.written_files:
                self.assertTrue(written_file.exists())

    def test_tabular_curves_reject_nonmonotonic_kr(self) -> None:
        tables = [
            {
                "curve_name": "bad_conductivity",
                "curve_kind": "conductivity",
                "points": [
                    {"saturation": 0.2, "relative_permeability": 0.0},
                    {"saturation": 0.6, "relative_permeability": 0.4},
                    {"saturation": 1.0, "relative_permeability": 0.3},
                ],
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            with self.assertRaises(ValueError):
                build_tabular_permeability_assets(
                    tables=tables,
                    workdir=Path(tmpdir),
                    theta_s=0.45,
                    ksat_m_s=1.0e-5,
                )

    def test_tabular_curves_generate_lookup_retention_and_pchip_permeability(self) -> None:
        tables = [
            {
                "curve_name": "lab_retention",
                "curve_kind": "retention",
                "points": [
                    {"saturation": 0.2, "pressure_pa": 100000.0},
                    {"saturation": 0.6, "pressure_pa": 20000.0},
                    {"saturation": 1.0, "pressure_pa": 0.0},
                ],
            },
            {
                "curve_name": "lab_conductivity",
                "curve_kind": "conductivity",
                "points": [
                    {"saturation": 0.2, "relative_permeability": 0.0},
                    {"saturation": 0.6, "relative_permeability": 0.25},
                    {"saturation": 1.0, "relative_permeability": 1.0},
                ],
            },
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            assets = build_tabular_characteristic_curve_assets(
                tables=tables,
                workdir=Path(tmpdir),
                theta_s=0.45,
                ksat_m_s=1.0e-5,
                rho=997.0,
                gravity=9.80665,
            )
            deck = "\n".join(assets.characteristic_curve_lines)
            retention_file = Path(tmpdir) / "retention_lab_retention.dat"

            self.assertIn("SATURATION_FUNCTION LOOKUP_TABLE", deck)
            self.assertIn("PERMEABILITY_FUNCTION PCHIP_LIQ", deck)
            self.assertIn("TIME_UNITS yr", retention_file.read_text(encoding="utf-8"))


class DemoDeckWriterTests(unittest.TestCase):
    def test_grid_builder_normalizes_xy_grid(self) -> None:
        grid = build_demo_grid(
            {
                "dimension": "2",
                "grid_plane": "XY",
                "length_x_m": 10,
                "length_y_m": 4,
                "depth_z_m": 2,
                "nx": 5,
                "ny": 4,
                "nz": 99,
            }
        )

        self.assertEqual(grid.dimension, "2d_xy")
        self.assertEqual((grid.nx, grid.ny, grid.nz), (5, 4, 1))
        self.assertAlmostEqual(grid.dx_m, 2.0)
        self.assertAlmostEqual(grid.dy_m, 1.0)

    def test_standard_deck_writer_matches_legacy_wrapper(self) -> None:
        input_json = Path("input/soilflow_pflotran_demo.json")
        params = read_params(input_json)
        weather = read_weather(input_json)
        derived = compute_derived(params, weather)

        self.assertEqual(generate_standard_pflotran_input(params, derived), generate_pflotran_input(params, derived))


class SurfaceBalanceTests(unittest.TestCase):
    def test_weather_row_keeps_transpiration_but_excludes_it_from_surface_flux(self) -> None:
        row = normalize_weather_row(
            {
                "date": "2026-06-16",
                "precipitation_mm_day": "10",
                "irrigation_mm_day": "2",
                "epot_mm_day": "3",
                "tpot_mm_day": "4",
                "groundwater_depth_m": "1.5",
            }
        )

        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["tpot_mm_day"], 4.0)
        self.assertEqual(row["net_surface_input_mm_day"], 9.0)

    def test_mean_top_flux_uses_override_or_weather_average(self) -> None:
        weather = [
            {"net_surface_input_mm_day": 8.64},
            {"net_surface_input_mm_day": 0.0},
        ]

        self.assertAlmostEqual(compute_mean_top_flux_m_s({}, weather), 5.0e-8)
        self.assertAlmostEqual(compute_mean_top_flux_m_s({"top_flux_override_m_s": "-1e-8"}, weather), -1.0e-8)

    def test_write_weather_csv_preserves_contract_columns(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "forcing_daily.csv"
            row = normalize_weather_row({"date": "2026-06-16", "precipitation_mm_day": 1})
            assert row is not None

            write_weather_csv([row], path)

            text = path.read_text(encoding="utf-8")
            self.assertIn("net_surface_input_mm_day", text)
            self.assertIn("2026-06-16", text)

    def test_simple_surface_flux_model_exposes_replaceable_interface(self) -> None:
        model = SimpleSurfaceFluxModel()
        weather_row = model.normalize_row({"date": "2026-06-16", "precipitation_mm_day": 8.64})
        assert weather_row is not None

        self.assertAlmostEqual(model.mean_top_flux_m_s({}, [weather_row]), 1.0e-7)


class ResultContractTests(unittest.TestCase):
    def test_profile_rows_are_converted_to_solver_neutral_contract(self) -> None:
        contract = profile_rows_to_contract(
            [{"z_m": 0.5, "pressure_pa": 101325.0, "saturation": 0.9}],
            source_solver="unit-test",
        )

        self.assertEqual(contract.status, "PARSED")
        self.assertEqual(contract.source_solver, "unit-test")
        self.assertEqual(contract.profiles[0].coordinate_m, 0.5)
        self.assertEqual(contract.profiles[0].pressure_pa, 101325.0)


class TestEvaluationTests(unittest.TestCase):
    def test_suite_status_accepts_generated_outputs_in_dry_run(self) -> None:
        result = SimpleNamespace(
            test_id="_test_linear_darcy",
            status="GENERATED",
            metrics={"verification_level": "strict_analytical"},
        )

        lines = suite_status_lines([result], dry_run=True)

        self.assertIn("TEST_SUITE_STATUS=DRY_RUN", lines)
        self.assertIn("tests_failed=0", lines)
        self.assertIn("strict_analytical_total=1", lines)
        self.assertIn("strict_analytical_passed=1", lines)

    def test_suite_status_writer_emits_text_json_and_csv_artifacts(self) -> None:
        result = SimpleNamespace(
            test_id="_test_richards_mms",
            status="PASS_WITH_WARNINGS",
            output_dir=Path("/tmp/_test_richards_mms"),
            metrics={
                "verification_level": "profile_smoke",
                "warning_count": 1,
                "profile_overlay_comparison": "REFERENCE_OVERLAY",
                "profile_overlay_points": 96,
                "profile_overlay_quality_check": "PASS",
                "profile_physics_family": "richards",
                "profile_carrier_status": "PROFILE_CARRIER_READY",
                "profile_deck_kind": "richards_profile_carrier",
                "strict_candidate_can_gate_suite": False,
                "strict_profile_evaluator": "EVALUATOR_READY_DECK_PENDING",
            },
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            suite_dir = Path(tmpdir)

            write_suite_status_file([result], suite_dir, dry_run=False)

            self.assertIn("TEST_SUITE_STATUS=PASS_WITH_WARNINGS", (suite_dir / "TEST_SUITE_STATUS.txt").read_text(encoding="utf-8"))
            self.assertIn('"profile_smoke_ready": 1', (suite_dir / "TEST_SUITE_STATUS.json").read_text(encoding="utf-8"))
            csv_text = (suite_dir / "TEST_SUITE_RESULTS.csv").read_text(encoding="utf-8")
            self.assertIn("profile_overlay_comparison", csv_text)
            self.assertIn("profile_overlay_quality_check", csv_text)
            self.assertIn("profile_physics_family", csv_text)
            self.assertIn("profile_carrier_status", csv_text)
            self.assertIn("profile_deck_kind", csv_text)
            self.assertIn("strict_candidate_can_gate_suite", csv_text)
            self.assertIn("strict_profile_evaluator", csv_text)
            self.assertIn("REFERENCE_OVERLAY", csv_text)


class TestRegistryTests(unittest.TestCase):
    def test_registry_selection_and_json_lookup(self) -> None:
        self.assertIn("linear_darcy", TEST_REGISTRY)
        self.assertEqual(selected_test_names("linear_darcy"), ["linear_darcy"])
        self.assertGreater(len(selected_test_names("all")), 1)
        params = test_params_from_document(
            {"test_scenarios": {"linear_darcy": {"column_height_m": 2.0}}},
            "linear_darcy",
        )
        self.assertEqual(params["column_height_m"], 2.0)

    def test_registry_preserves_cli_workdir_contract(self) -> None:
        explicit = Path("/tmp/explicit")

        self.assertEqual(
            test_workdir_for(
                test_name="linear_darcy",
                output_dir=None,
                workdir=explicit,
                selected_test="linear_darcy",
            ),
            explicit,
        )
        self.assertEqual(suite_workdir_for(Path("/tmp/out")), Path("/tmp/out/runs/_test_suite"))

    def test_registry_declares_verification_levels(self) -> None:
        self.assertEqual(verification_level_for_test("linear_darcy"), "strict_analytical")
        self.assertEqual(verification_level_for_test("transient_uniform_storage_vg"), "partial_balance")
        self.assertEqual(verification_level_for_test("theis_radial_flow"), "profile_smoke")


class TestArtifactsTests(unittest.TestCase):
    def test_csv_svg_and_overlay_diagnostics_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            rows = [{"time_days": 0.0, "value": 1.0}]

            write_rows_csv(workdir / "rows.csv", rows)
            write_curve_svg(workdir / "curve.svg", "Title", "t", "v", rows, "time_days", "value")
            write_rows_csv(
                workdir / "analytical_profiles.csv",
                [{"depth_m": 0.1, "theta_m3_m3": 0.3, "pressure_head_m": -1.0}],
            )
            diagnostics = analytical_profile_overlay_diagnostics(workdir)

            self.assertIn("time_days", (workdir / "rows.csv").read_text(encoding="utf-8"))
            self.assertIn("<svg", (workdir / "curve.svg").read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["analytical_overlay_check"], "PASS")


class ProfileBenchmarkTests(unittest.TestCase):
    def test_richards_profile_overlay_rows_are_written_for_mms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)

            write_richards_profile_analytical_profiles("richards_mms", workdir)
            text = (workdir / "analytical_profiles.csv").read_text(encoding="utf-8")

            self.assertIn("pressure_head_m", text)
            self.assertIn("theta_m3_m3", text)

    def test_profile_status_fields_use_tecpot_profile_and_overlay(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            (workdir / "pflotran-001.tec").write_text(
                "\n".join(
                    [
                        'VARIABLES = "X [m]", "Y [m]", "Z [m]", "Liquid Pressure [Pa]", "Liquid Saturation"',
                        "ZONE T=\"0\"",
                        "0 0 0.25 101000 0.90",
                        "0 0 0.75 99000 0.80",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            write_rows_csv(
                workdir / "analytical_profiles.csv",
                [{"depth_m": 0.1, "theta_m3_m3": 0.3, "pressure_head_m": -1.0}],
            )

            fields = profile_status_fields_after_run("richards_mms", workdir)

            self.assertEqual(fields["verification_level"], "profile_smoke")
            self.assertEqual(fields["profile_status"], "TECPLOT_READY")
            self.assertEqual(fields["analytical_overlay_check"], "PASS")
            self.assertEqual(fields["profile_points"], 2)
            self.assertEqual(fields["profile_overlay_comparison"], "REFERENCE_OVERLAY")
            self.assertEqual(fields["profile_overlay_points"], 2)
            self.assertEqual(fields["profile_overlay_source"], "profile_overlay_comparison.csv")
            self.assertEqual(fields["profile_evaluator"], "reference_overlay")
            self.assertEqual(fields["strict_profile_evaluator"], "EVALUATOR_READY_DECK_PENDING")
            self.assertEqual(fields["profile_physics_family"], "richards")
            self.assertEqual(fields["profile_carrier_status"], "PROFILE_CARRIER_READY")
            self.assertEqual(fields["profile_deck_kind"], "richards_profile_carrier")
            self.assertFalse(fields["strict_candidate_can_gate_suite"])
            self.assertIn("MMS source-term", str(fields["strict_profile_evaluator_blocker"]))
            self.assertEqual(fields["profile_overlay_quality_check"], "PASS")
            self.assertEqual(fields["richards_mms_strict_evaluator"], "READY_DECK_PENDING")
            self.assertEqual(fields["richards_mms_strict_candidate_check"], "FAIL")
            self.assertTrue((workdir / "profile_overlay_comparison.csv").exists())

    def test_profile_overlay_metrics_compare_numerical_and_reference_profiles(self) -> None:
        metrics = profile_overlay_error_metrics(
            [
                {"z_m": 0.0, "pressure_pa": 101325.0, "saturation": 0.5},
                {"z_m": 1.0, "pressure_pa": 101325.0, "saturation": 0.5},
            ],
            [
                {"depth_m": 0.0, "theta_m3_m3": 0.215, "pressure_head_m": 0.0},
                {"depth_m": 1.0, "theta_m3_m3": 0.215, "pressure_head_m": 0.0},
            ],
        )

        self.assertEqual(metrics["profile_overlay_comparison"], "REFERENCE_OVERLAY")
        self.assertEqual(metrics["profile_overlay_points"], 2)
        self.assertEqual(metrics["theta_overlay_max_abs_m3_m3"], "0")

    def test_profile_overlay_comparison_csv_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)

            metrics = write_profile_overlay_comparison(
                workdir,
                [
                    {"z_m": 0.0, "pressure_pa": 101325.0, "saturation": 0.5},
                    {"z_m": 1.0, "pressure_pa": 101325.0, "saturation": 0.5},
                ],
                [
                    {"depth_m": 0.0, "theta_m3_m3": 0.215, "pressure_head_m": 0.0},
                    {"depth_m": 1.0, "theta_m3_m3": 0.215, "pressure_head_m": 0.0},
                ],
            )

            text = (workdir / "profile_overlay_comparison.csv").read_text(encoding="utf-8")
            self.assertEqual(metrics["profile_overlay_source"], "profile_overlay_comparison.csv")
            self.assertIn("theta_numerical_m3_m3", text)

    def test_profile_overlay_quality_evaluator_classifies_pass_warn_and_skip(self) -> None:
        passing = evaluate_reference_overlay_quality(
            {
                "profile_overlay_comparison": "REFERENCE_OVERLAY",
                "theta_overlay_max_abs_m3_m3": "0.01",
                "pressure_head_overlay_max_abs_m": "0.5",
            }
        )
        warning = evaluate_reference_overlay_quality(
            {
                "profile_overlay_comparison": "REFERENCE_OVERLAY",
                "theta_overlay_max_abs_m3_m3": "0.8",
                "pressure_head_overlay_max_abs_m": "0.5",
            }
        )
        skipped = evaluate_reference_overlay_quality({"profile_overlay_comparison": "SKIP"})

        self.assertEqual(passing["profile_overlay_quality_check"], "PASS")
        self.assertEqual(warning["profile_overlay_quality_check"], "WARN")
        self.assertEqual(skipped["profile_overlay_quality_check"], "SKIP")

    def test_richards_mms_strict_candidate_uses_tight_overlay_tolerances(self) -> None:
        passing = evaluate_richards_mms_strict_candidate(
            {
                "profile_overlay_comparison": "REFERENCE_OVERLAY",
                "theta_overlay_rmse_m3_m3": "0.01",
                "theta_overlay_max_abs_m3_m3": "0.02",
                "pressure_head_overlay_rmse_m": "0.01",
                "pressure_head_overlay_max_abs_m": "0.02",
            }
        )
        failing = evaluate_richards_mms_strict_candidate(
            {
                "profile_overlay_comparison": "REFERENCE_OVERLAY",
                "theta_overlay_rmse_m3_m3": "0.01",
                "theta_overlay_max_abs_m3_m3": "0.02",
                "pressure_head_overlay_rmse_m": "0.01",
                "pressure_head_overlay_max_abs_m": "0.2",
            }
        )

        self.assertEqual(passing["richards_mms_strict_evaluator"], "READY_DECK_PENDING")
        self.assertEqual(passing["richards_mms_strict_candidate_check"], "PASS")
        self.assertEqual(failing["richards_mms_strict_candidate_check"], "FAIL")

    def test_profile_benchmark_case_metadata_declares_strict_evaluator_blockers(self) -> None:
        richards = profile_benchmark_case_status_fields("richards_mms")
        heat = profile_benchmark_case_status_fields("heat_conduction_1d")

        self.assertEqual(richards["profile_physics_family"], "richards")
        self.assertEqual(richards["profile_carrier_status"], "PROFILE_CARRIER_READY")
        self.assertEqual(richards["profile_deck_kind"], "richards_profile_carrier")
        self.assertFalse(richards["strict_candidate_can_gate_suite"])
        self.assertEqual(richards["strict_profile_evaluator"], "EVALUATOR_READY_DECK_PENDING")
        self.assertEqual(heat["profile_carrier_status"], "REFERENCE_ONLY")

    def test_profile_benchmark_case_manifest_is_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = write_profile_benchmark_case_manifest("richards_mms", Path(tmpdir))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["profile_deck_kind"], "richards_profile_carrier")
            self.assertFalse(manifest["strict_candidate_can_gate_suite"])


class ResultDiagnosticsTests(unittest.TestCase):
    def test_parse_tecpotran_records_and_aggregate_by_z(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tec_path = Path(tmpdir) / "pflotran-001.tec"
            tec_path.write_text(
                "\n".join(
                    [
                        'VARIABLES = "X [m]", "Y [m]", "Z [m]", "Liquid Pressure [Pa]", "Liquid Saturation"',
                        "ZONE T=\"0\"",
                        "0 0 0.25 101000 0.90",
                        "1 0 0.25 103000 0.94",
                        "0 0 0.75 99000 0.80",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            variables, rows = parse_tecpotran_tec(tec_path)
            _, records = load_tecpotran_records(Path(tmpdir))
            converted = records_to_z_pressure_saturation(records)

            self.assertIn("Liquid Pressure [Pa]", variables)
            self.assertEqual(len(rows), 3)
            self.assertEqual(len(converted), 2)
            self.assertAlmostEqual(converted[0]["pressure_pa"], 102000.0)
            self.assertAlmostEqual(converted[0]["saturation"], 0.92)

    def test_solver_warning_and_status_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "run_pflotran.log"
            log_path.write_text(
                "\n".join(
                    [
                        "WARNING: Mualem-van Genuchten relative permeability function is being used without SMOOTH option",
                        "Step 1 Time= 1.0D-03 newton = 3 linear = 11 cuts = 0",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            status_path = Path(tmpdir) / "TEST_STATUS.txt"

            warnings = classify_pflotran_warnings(log_path, "hydrostatic_vg_no_flow")
            solver = parse_pflotran_solver_diagnostics(log_path)
            write_unified_status(status_path, {"ok": True, "status": combined_test_status(True, True, str(warnings["warning_check"]))})

            self.assertEqual(warnings["warning_check"], "WARN")
            self.assertEqual(solver["solver_cuts"], 0)
            self.assertEqual(solver["flow_ts_newton_iterations"], 3)
            self.assertIn("ok=true", status_path.read_text(encoding="utf-8"))
            self.assertIn("status=PASS_WITH_WARNINGS", status_path.read_text(encoding="utf-8"))

    def test_direct_flux_probe_reads_velocity_tec(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            vel_path = Path(tmpdir) / "pflotran-vel-001.tec"
            vel_path.write_text(
                "\n".join(
                    [
                        'VARIABLES = "X [m]", "Y [m]", "Z [m]", "QLZ"',
                        "0 0 0 -0.0864",
                        "0 0 1 -0.0864",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            probe = direct_flux_output_probe(Path(tmpdir))

            self.assertTrue(probe["parseable"])
            self.assertAlmostEqual(float(probe["q_direct_m_s"]), -1.0e-6)

    def test_fit_line_slope(self) -> None:
        self.assertAlmostEqual(fit_line_slope([0.0, 1.0, 2.0], [1.0, 3.0, 5.0]), 2.0)


class SolverRunnerTests(unittest.TestCase):
    def test_find_pflotran_native_prefers_cli_executable(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            executable = Path(tmpdir) / "fake_pflotran.sh"
            executable.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)

            self.assertEqual(find_pflotran_native({}, str(executable)), str(executable))

    def test_run_native_returns_external_solver_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            executable = tmpdir_path / "fake_pflotran.sh"
            executable.write_text("#!/usr/bin/env sh\necho fake solver\nexit 7\n", encoding="utf-8")
            executable.chmod(0o755)
            (tmpdir_path / "pflotran.in").write_text("# smoke\n", encoding="utf-8")

            self.assertEqual(run_native(tmpdir_path, str(executable), 0), 7)
            self.assertIn("fake solver", (tmpdir_path / "run_pflotran.log").read_text(encoding="utf-8"))

    def test_test_solver_execution_reports_missing_and_nonzero_solver(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            args = SimpleNamespace(pflotran_exe=str(workdir / "missing"), prefer_wsl=False)

            missing = execute_test_solver(args, "linear_darcy", workdir, mpi_processes=1)

            self.assertEqual(missing.status, "GENERATED_ONLY")
            self.assertFalse(missing.executed)
            self.assertIn("GENERATED_ONLY", (workdir / "TEST_STATUS.txt").read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as tmpdir:
            workdir = Path(tmpdir)
            executable = workdir / "fake_pflotran.sh"
            executable.write_text("#!/usr/bin/env sh\nexit 7\n", encoding="utf-8")
            executable.chmod(0o755)
            (workdir / "pflotran.in").write_text("# smoke\n", encoding="utf-8")
            args = SimpleNamespace(pflotran_exe=str(executable), prefer_wsl=False)

            failed = execute_test_solver(args, "linear_darcy", workdir, mpi_processes=1)

            self.assertEqual(failed.status, "PFLOTRAN_ERROR")
            self.assertTrue(failed.executed)
            self.assertEqual(failed.exit_code, 7)


class CliContractTests(unittest.TestCase):
    def test_demo_mode_returns_native_pflotran_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            fake_pflotran = tmpdir_path / "fake_pflotran.sh"
            fake_pflotran.write_text("#!/usr/bin/env sh\necho fake pflotran\nexit 7\n", encoding="utf-8")
            fake_pflotran.chmod(0o755)
            args = SimpleNamespace(
                input_json=Path("input/soilflow_pflotran_demo.json"),
                workdir=tmpdir_path / "run",
                dry_run=False,
                run=True,
                pflotran_exe=fake_pflotran,
                prefer_wsl=False,
            )

            self.assertEqual(run_demo_mode(args), 7)


if __name__ == "__main__":
    unittest.main()

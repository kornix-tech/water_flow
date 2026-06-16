from __future__ import annotations

import sys
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
    validate_soil_model_pair,
)
from soilflow_pflotran_modules.profile_carrier import generate_richards_profile_input
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
from soilflow_pflotran_modules.solver_runner import find_pflotran_native, run_native
from soilflow_pflotran_modules.surface_balance import (
    SimpleSurfaceFluxModel,
    compute_mean_top_flux_m_s,
    normalize_weather_row,
    write_weather_csv,
)
from soilflow_pflotran_modules.tabular_curves import build_tabular_characteristic_curve_assets, build_tabular_permeability_assets
from soilflow_pflotran_modules.test_evaluation import combined_test_status, suite_status_lines
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
        result = SimpleNamespace(test_id="_test_linear_darcy", status="GENERATED", metrics={})

        lines = suite_status_lines([result], dry_run=True)

        self.assertIn("TEST_SUITE_STATUS=DRY_RUN", lines)
        self.assertIn("tests_failed=0", lines)


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

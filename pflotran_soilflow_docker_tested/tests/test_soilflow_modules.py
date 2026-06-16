from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from soilflow_pflotran_modules.input_contract import as_bool, as_float, as_int, optional_float, pf_float
from soilflow_pflotran_modules.extended_analytical import (
    buckley_fractional_flow,
    generate_extended_analytical_rows,
    generate_normalized_profile_rows,
    green_ampt_cumulative_infiltration,
)
from soilflow_pflotran_modules.physical_models import (
    model_pair_label,
    normalize_grid_dimension,
    normalize_model_token,
    validate_soil_model_pair,
)
from soilflow_pflotran_modules.profile_carrier import generate_richards_profile_input
from soilflow_pflotran_modules.tabular_curves import build_tabular_permeability_assets


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


if __name__ == "__main__":
    unittest.main()

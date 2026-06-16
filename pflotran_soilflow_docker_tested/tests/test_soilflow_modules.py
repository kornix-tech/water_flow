from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from soilflow_pflotran_modules.input_contract import as_bool, as_float, as_int, optional_float, pf_float
from soilflow_pflotran_modules.physical_models import (
    model_pair_label,
    normalize_grid_dimension,
    normalize_model_token,
    validate_soil_model_pair,
)


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


if __name__ == "__main__":
    unittest.main()

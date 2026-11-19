"""T3 tests — dates.py (RED first)."""
import unittest
from datetime import date

from driphound.dates import infer_order, parse_date
from driphound.errors import ParseError


class TestParseDate(unittest.TestCase):
    def test_formats(self):
        cases = {
            "2025-01-05": date(2025, 1, 5),
            "01/05/2025": date(2025, 1, 5),   # MDY default when order hint None and unambiguous
            "05/01/2025": date(2025, 5, 1),   # DMY when hint says DMY
            "2025/01/05": date(2025, 1, 5),
            "05.01.2025": date(2025, 5, 1),   # dots default DMY (EU style)
            "Jan 5, 2025": date(2025, 1, 5),
            "5 January 2025": date(2025, 1, 5),
            "05-JAN-25": date(2025, 1, 5),
            "20250105": date(2025, 1, 5),
        }
        for s, want in cases.items():
            self.assertEqual(parse_date(s), want, s)

    def test_order_hint_overrides(self):
        self.assertEqual(parse_date("03/04/2025", order="MDY"), date(2025, 3, 4))
        self.assertEqual(parse_date("03/04/2025", order="DMY"), date(2025, 4, 3))
        self.assertEqual(parse_date("2025-03-04", order="YMD"), date(2025, 3, 4))

    def test_two_digit_years_pivot(self):
        self.assertEqual(parse_date("01/05/25", order="MDY"), date(2025, 1, 5))
        self.assertEqual(parse_date("01/05/99", order="MDY"), date(1999, 1, 5))
        self.assertEqual(parse_date("01/05/50", order="MDY"), date(1950, 1, 5))
        self.assertEqual(parse_date("01/05/49", order="MDY"), date(2049, 1, 5))

    def test_epoch(self):
        self.assertEqual(parse_date("1735689600"), date(2025, 1, 1))      # seconds
        self.assertEqual(parse_date("1735689600000"), date(2025, 1, 1))   # millis

    def test_invalid(self):
        for bad in ("", "not-a-date", "13/13/2025", "2025-02-30", "00/00/0000", "2025-1-"):
            with self.assertRaises(ParseError, msg=repr(bad)):
                parse_date(bad)


class TestInferOrder(unittest.TestCase):
    def test_unambiguous_first_component_gt_12(self):
        self.assertEqual(infer_order(["13/01/2025", "25/12/2024"]), "DMY")
        self.assertEqual(infer_order(["01/13/2025", "12/25/2024"]), "MDY")

    def test_year_first(self):
        self.assertEqual(infer_order(["2025-01-13", "2024-12-25"]), "YMD")

    def test_ambiguous_returns_none(self):
        self.assertIsNone(infer_order(["01/02/2025", "03/04/2025"]))

    def test_garbage_ignored(self):
        self.assertEqual(infer_order(["junk", "22/11/2025", ""]), "DMY")
        self.assertIsNone(infer_order(["junk", ""]))


if __name__ == "__main__":
    unittest.main()

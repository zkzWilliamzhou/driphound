"""T4 tests — ingest/mapping.py (RED first)."""
import tempfile
import unittest
from pathlib import Path

from driphound.errors import MappingError
from driphound.ingest.mapping import (ColumnMapping, delete_profile, infer_columns,
                                      list_profiles, load_profile, save_profile)


class TestInfer(unittest.TestCase):
    def test_english_header(self):
        header = ["Date", "Description", "Amount", "Balance"]
        rows = [["01/05/2025", "NETFLIX.COM", "-15.99", "1000.00"]]
        m = infer_columns(header, rows)
        self.assertEqual((m.date, m.merchant, m.amount, m.balance), (0, 1, 2, 3))

    def test_debit_credit_pair(self):
        header = ["Posted Date", "Payee", "Debit", "Credit"]
        rows = [["2025-01-05", "SPOTIFY", "9.99", ""], ["2025-01-06", "PAYROLL", "", "2500.00"]]
        m = infer_columns(header, rows)
        self.assertIsNotNone(m.debit)
        self.assertIsNotNone(m.credit)
        self.assertEqual(m.date, 0)
        self.assertEqual(m.merchant, 1)

    def test_nonenglish_header(self):
        header = ["Datum", "Beschreibung", "Betrag"]
        rows = [["05.01.2025", "NETFLIX", "-15,99"]]
        m = infer_columns(header, rows)
        self.assertEqual((m.date, m.merchant, m.amount), (0, 1, 2))

    def test_content_based_no_header(self):
        rows = [["01/05/2025", "NETFLIX.COM", "-15.99"],
                ["01/06/2025", "UBER EATS", "-22.10"]]
        m = infer_columns([], rows)
        self.assertEqual((m.date, m.merchant, m.amount), (0, 1, 2))

    def test_missing_essential_raises_with_suggestions(self):
        with self.assertRaises(MappingError) as ctx:
            infer_columns(["Foo", "Bar"], [["x", "y"], ["z", "w"]])
        self.assertIn("Foo", str(ctx.exception))

    def test_amount_column_never_merchant(self):
        header = ["Date", "Amount", "Description"]
        rows = [["2025-01-05", "-15.99", "CAFE"]]
        m = infer_columns(header, rows)
        self.assertEqual(m.amount, 1)
        self.assertEqual(m.merchant, 2)


class TestProfiles(unittest.TestCase):
    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            m = ColumnMapping(date=2, merchant=0, amount=1)
            save_profile("mybank", m, directory=td, extra={"date_order": "DMY"})
            self.assertIn("mybank", list_profiles(directory=td))
            loaded, extra = load_profile("mybank", directory=td)
            self.assertEqual(loaded.date, 2)
            self.assertEqual(loaded.merchant, 0)
            self.assertEqual(loaded.amount, 1)
            self.assertEqual(extra["date_order"], "DMY")
            delete_profile("mybank", directory=td)
            self.assertEqual(list_profiles(directory=td), [])

    def test_missing_profile(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(MappingError):
                load_profile("nope", directory=td)

    def test_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(MappingError):
                save_profile("../evil", ColumnMapping(date=0, merchant=1, amount=2), directory=td)


if __name__ == "__main__":
    unittest.main()

"""T1 tests — model.py + errors.py (written FIRST, must go RED before implementation)."""
import unittest

from driphound.errors import DripHoundError, IngestError, MappingError, ParseError
from driphound.model import Finding, Report, Statement, Tx


class TestTx(unittest.TestCase):
    def test_stable_id_from_content(self):
        a = Tx(date="2025-01-05", amount_cents=-1499, currency="USD",
               merchant_raw="NETFLIX.COM", memo="", account="chk", source="f.csv", line=3)
        b = Tx(date="2025-01-05", amount_cents=-1499, currency="USD",
               merchant_raw="NETFLIX.COM", memo="", account="chk", source="f.csv", line=3)
        c = Tx(date="2025-01-05", amount_cents=-1499, currency="USD",
               merchant_raw="NETFLIX.COM", memo="", account="chk", source="f.csv", line=4)
        self.assertEqual(a.id, b.id)
        self.assertNotEqual(a.id, c.id)
        self.assertEqual(len(a.id), 16)

    def test_amount_is_int_cents(self):
        t = Tx(date="2025-01-05", amount_cents=-1499, currency="USD", merchant_raw="X",
               memo="", account="chk", source="f", line=1)
        self.assertIsInstance(t.amount_cents, int)
        self.assertTrue(t.is_debit())
        with self.assertRaises(TypeError):
            Tx(date="2025-01-05", amount_cents=-14.99, currency="USD", merchant_raw="X",
               memo="", account="chk", source="f", line=1)

    def test_merchant_norm_defaults_to_raw(self):
        t = Tx(date="2025-01-05", amount_cents=100, currency=None, merchant_raw="  Cafe X ",
               memo="", account="", source="f", line=1)
        self.assertEqual(t.merchant_norm, "cafe x")


class TestStatement(unittest.TestCase):
    def test_aggregates_and_currency_guard(self):
        s = Statement(source="f.csv", format="csv")
        s.add(Tx(date="2025-01-05", amount_cents=-1000, currency="USD", merchant_raw="A",
                 memo="", account="chk", source="f.csv", line=1))
        s.add(Tx(date="2025-02-05", amount_cents=-500, currency="EUR", merchant_raw="B",
                 memo="", account="chk", source="f.csv", line=2))
        self.assertEqual(len(s.transactions), 2)
        self.assertEqual(sorted(s.currencies()), ["EUR", "USD"])
        totals = s.debit_totals_by_currency()
        self.assertEqual(totals, {"USD": 1000, "EUR": 500})
        self.assertTrue(s.warnings)  # mixed currency warning recorded

    def test_date_range(self):
        s = Statement(source="f.csv", format="csv")
        s.add(Tx(date="2025-03-05", amount_cents=1, currency=None, merchant_raw="A",
                 memo="", account="", source="f.csv", line=1))
        s.add(Tx(date="2025-01-05", amount_cents=1, currency=None, merchant_raw="A",
                 memo="", account="", source="f.csv", line=2))
        self.assertEqual(s.date_range(), ("2025-01-05", "2025-03-05"))


class TestFinding(unittest.TestCase):
    def test_construction_and_validation(self):
        f = Finding(kind="recurring", severity="medium", confidence=0.9,
                    title="Netflix", detail="why", evidence=["abc123"],
                    annualized_cents=17988, currency="USD")
        self.assertEqual(f.kind, "recurring")
        self.assertTrue(0.0 <= f.confidence <= 1.0)
        with self.assertRaises(ValueError):
            Finding(kind="recurring", severity="medium", confidence=1.5, title="t",
                    detail="d", evidence=[], annualized_cents=0, currency="USD")
        with self.assertRaises(ValueError):
            Finding(kind="recurring", severity="BOOM", confidence=0.5, title="t",
                    detail="d", evidence=[], annualized_cents=0, currency="USD")

    def test_stable_id(self):
        kw = dict(kind="fees", severity="low", confidence=0.8, title="ATM fee",
                  detail="d", evidence=["t1"], annualized_cents=0, currency="USD")
        self.assertEqual(Finding(**kw).id, Finding(**kw).id)


class TestReport(unittest.TestCase):
    def test_report_totals_cents_only(self):
        r = Report(version="0.0.0")
        f1 = Finding(kind="recurring", severity="high", confidence=0.95, title="A", detail="",
                     evidence=[], annualized_cents=12000, currency="USD")
        f2 = Finding(kind="zombie", severity="low", confidence=0.6, title="B", detail="",
                     evidence=[], annualized_cents=3600, currency="USD")
        f3 = Finding(kind="recurring", severity="high", confidence=0.95, title="C", detail="",
                     evidence=[], annualized_cents=999, currency="EUR")
        r.findings.extend([f1, f2, f3])
        self.assertEqual(r.annualized_leak_cents("USD"), 15600)
        with self.assertRaises(DripHoundError):
            r.annualized_leak_cents()  # refuses to mix currencies when >1 present

    def test_error_hierarchy(self):
        for e in (IngestError, MappingError, ParseError):
            self.assertTrue(issubclass(e, DripHoundError))


if __name__ == "__main__":
    unittest.main()

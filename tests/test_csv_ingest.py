"""T5 tests — ingest/csving.py (RED first)."""
import tempfile
import unittest
from pathlib import Path

from driphound.errors import IngestError, MappingError
from driphound.ingest.csving import load_csv


def _write(dirpath, name, content, encoding="utf-8"):
    p = Path(dirpath) / name
    data = content.encode(encoding) if isinstance(content, str) else content
    p.write_bytes(data)
    return str(p)


class TestCsvBasics(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.mkdtemp()

    def test_standard_us(self):
        p = _write(self.td, "a.csv", "Date,Description,Amount\n01/05/2025,NETFLIX.COM,-15.99\n01/06/2025,PAYROLL,2500.00\n")
        st = load_csv(p)
        self.assertEqual(len(st.transactions), 2)
        t = st.transactions[0]
        self.assertEqual(t.amount_cents, -1599)
        self.assertIsNone(t.currency)  # no symbol in file, none passed -> unknown
        self.assertEqual(t.merchant_norm, "netflix")  # alias applied
        self.assertEqual(t.date, "2025-01-05")
        self.assertEqual(t.line, 2)

    def test_debit_credit_columns(self):
        p = _write(self.td, "b.csv",
                   "Date,Payee,Debit,Credit\n2025-01-05,SPOTIFY,9.99,\n2025-01-06,PAYROLL,,2500.00\n")
        st = load_csv(p)
        self.assertEqual(st.transactions[0].amount_cents, -999)
        self.assertEqual(st.transactions[1].amount_cents, 250000)

    def test_type_column_sign(self):
        p = _write(self.td, "c.csv",
                   "Date,Description,Amount,Type\n2025-01-05,SPOTIFY,9.99,Debit\n2025-01-06,PAYROLL,2500.00,Credit\n")
        st = load_csv(p)
        self.assertEqual(st.transactions[0].amount_cents, -999)
        self.assertEqual(st.transactions[1].amount_cents, 250000)

    def test_european_semicolon(self):
        p = _write(self.td, "d.csv",
                   "Datum;Beschreibung;Betrag\n05.01.2025;NETFLIX.COM;-15,99\n06.02.2025;UBER;-22,10\n")
        st = load_csv(p)
        self.assertEqual(st.meta.get("delimiter"), ";")
        self.assertEqual(st.transactions[0].amount_cents, -1599)
        self.assertEqual(st.transactions[0].date, "2025-01-05")
        self.assertEqual(st.meta.get("date_order_inferred"), "DMY")

    def test_preamble_and_footer_skipped(self):
        p = _write(self.td, "e.csv",
                   "FIRST NATIONAL BANK\nStatement for January 2025\n\n"
                   "Date,Description,Amount\n01/05/2025,NETFLIX,-15.99\n\n"
                   "Total,-15.99\nThank you for banking with us\n")
        st = load_csv(p)
        self.assertEqual(len(st.transactions), 1)
        self.assertTrue(st.meta.get("skipped_rows", 0) >= 3)

    def test_bom_crlf(self):
        p = _write(self.td, "f.csv", b"\xef\xbb\xbfDate,Description,Amount\r\n01/05/2025,NETFLIX,-15.99\r\n")
        st = load_csv(p)
        self.assertEqual(len(st.transactions), 1)

    def test_quoted_fields(self):
        p = _write(self.td, "g.csv",
                   'Date,Description,Amount\n01/05/2025,"ACME, INC. ""MAIN""",-15.99\n')
        st = load_csv(p)
        self.assertIn("ACME", st.transactions[0].merchant_raw)

    def test_balance_sign_convention_detection(self):
        # debits exported POSITIVE; balance column proves direction: flip needed
        p = _write(self.td, "h.csv",
                   "Date,Description,Amount,Balance\n"
                   "2025-01-01,OPENING,0,1000.00\n"
                   "2025-01-05,NETFLIX,15.99,984.01\n"
                   "2025-01-06,PAYROLL,2500.00,3484.01\n")
        st = load_csv(p, sign_hint="auto")
        amts = {t.merchant_norm: t.amount_cents for t in st.transactions}
        self.assertEqual(amts["netflix"], -1599)   # flipped to debit by balance reconstruction
        self.assertEqual(amts["payroll"], 250000)  # stays credit... wait PAYROLL +2500 vs balance +2500 ✓

    def test_headerless_content_inference_succeeds(self):
        # Ruling (Boss): unambiguous columns can be inferred from content; headerless is legal.
        p = _write(self.td, "i.csv", "01/05/2025,NETFLIX,-15.99\n01/06/2025,UBER EATS,-22.10\n")
        st = load_csv(p)
        self.assertEqual(len(st.transactions), 2)
        self.assertIsNone(st.meta.get("header_row"))

    def test_headerless_ambiguous_raises(self):
        p = _write(self.td, "i2.csv", "aaa,bbb\nccc,ddd\neee,fff\n")
        with self.assertRaises((MappingError, IngestError)):
            load_csv(p)

    def test_mostly_unparseable_raises(self):
        p = _write(self.td, "j.csv", "Date,Description,Amount\n" + "junk,row,here\n" * 30 + "01/05/2025,NETFLIX,-15.99\n")
        with self.assertRaises(IngestError):
            load_csv(p)

    def test_ambiguous_dates_warn(self):
        p = _write(self.td, "k.csv", "Date,Description,Amount\n01/02/2025,NETFLIX,-15.99\n03/04/2025,UBER,-22.10\n")
        st = load_csv(p)
        self.assertTrue(st.meta.get("ambiguous_dates"))
        st2 = load_csv(p, date_order="DMY")
        self.assertEqual(st2.transactions[0].date, "2025-02-01")

    def test_explicit_currency(self):
        p = _write(self.td, "l.csv", "Date,Description,Amount\n2025-01-05,CAFE,-4.50\n")
        st = load_csv(p, currency="EUR")
        self.assertEqual(st.transactions[0].currency, "EUR")

    def test_empty_file(self):
        p = _write(self.td, "m.csv", "")
        with self.assertRaises(IngestError):
            load_csv(p)

    def test_missing_file(self):
        with self.assertRaises(IngestError):
            load_csv("/nonexistent/x.csv")


if __name__ == "__main__":
    unittest.main()

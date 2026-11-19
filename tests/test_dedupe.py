"""T6 tests — normalize/dedupe.py (RED first)."""
import unittest

from driphound.model import Tx
from driphound.normalize.dedupe import dedupe, tx_key


def _tx(date, cents, merchant, source="a.csv", line=1, memo=""):
    return Tx(date=date, amount_cents=cents, currency="USD", merchant_raw=merchant,
              memo=memo, account="chk", source=source, line=line)


class TestDedupe(unittest.TestCase):
    def test_key_ignores_source_and_line(self):
        a = _tx("2025-01-05", -1499, "NETFLIX", "x.csv", 3)
        b = _tx("2025-01-05", -1499, "netflix", "y.csv", 99)
        self.assertEqual(tx_key(a), tx_key(b))

    def test_dedupe_keeps_first_stable(self):
        a = _tx("2025-01-05", -1499, "NETFLIX", "x.csv", 3)
        b = _tx("2025-01-05", -1499, "NETFLIX", "x.csv", 4)  # same file dup line
        c = _tx("2025-01-06", -1499, "NETFLIX", "x.csv", 5)  # different day: real double-charge!
        kept, removed = dedupe([a, b, c])
        self.assertEqual(len(kept), 2)
        self.assertEqual(len(removed), 1)
        self.assertIn(c.id, {t.id for t in kept})

    def test_different_amount_not_dup(self):
        a = _tx("2025-01-05", -1499, "NETFLIX")
        b = _tx("2025-01-05", -1599, "NETFLIX")
        kept, removed = dedupe([a, b])
        self.assertEqual(len(kept), 2)
        self.assertEqual(removed, [])

    def test_memo_difference_does_not_split_key(self):
        a = _tx("2025-01-05", -1499, "NETFLIX", memo="card 1234")
        b = _tx("2025-01-05", -1499, "NETFLIX", memo="")
        kept, removed = dedupe([a, b])
        self.assertEqual(len(kept), 1)


if __name__ == "__main__":
    unittest.main()

"""T6 tests — normalize/merchant.py (RED first)."""
import unittest

from driphound.normalize.merchant import alias_of, clean_merchant, cluster_merchants


class TestClean(unittest.TestCase):
    def test_pos_prefixes_and_tails(self):
        self.assertEqual(clean_merchant("VISA POS PUR 5693 NETFLIX.COM LOS GATOS CA"), "netflix.com")
        self.assertEqual(clean_merchant("DEBIT PURCHASE - VISA 1234 SPOTIFY AB"), "spotify ab")
        self.assertEqual(clean_merchant("SQ *UBER EATS 123 HELP.UBER.COM CA"), "uber eats")
        self.assertEqual(clean_merchant("PAYPAL *SPOTIFY AB"), "spotify ab")
        self.assertEqual(clean_merchant("AMZN Mktp US*1A2B3C4D"), "amzn mktp us")
        self.assertEqual(clean_merchant("TST* CAFE AROMA"), "cafe aroma")

    def test_business_suffixes(self):
        self.assertEqual(clean_merchant("ACME FITNESS LLC"), "acme fitness")
        self.assertEqual(clean_merchant("ACME FITNESS, INC."), "acme fitness")
        self.assertEqual(clean_merchant("  Bob's   Bagels   Corp  "), "bob's bagels")

    def test_date_and_ref_tokens(self):
        self.assertEqual(clean_merchant("20250105 GYM CO"), "gym")
        self.assertEqual(clean_merchant("R123456789 GYM CO"), "gym")

    def test_alias(self):
        self.assertEqual(alias_of(clean_merchant("NETFLIX.COM")), "netflix")
        self.assertEqual(alias_of(clean_merchant("NF*NETFLIX.COM")), "netflix")
        self.assertEqual(alias_of(clean_merchant("AMZN Mktp US*1A2B3C4D")), "amazon")
        self.assertEqual(alias_of("some unknown vendor"), "some unknown vendor")


class TestCluster(unittest.TestCase):
    def test_fuzzy_merge_deterministic(self):
        names = ["WALMART", "WAL-MART", "WAL MART", "TARGET", "walmarT"]
        m1 = cluster_merchants(names)
        m2 = cluster_merchants(list(reversed(names)))
        self.assertEqual(m1, m2)  # order-independent
        self.assertEqual(m1["WALMART"], m1["WAL-MART"])
        self.assertEqual(m1["WALMART"], m1["WAL MART"])
        self.assertEqual(m1["WALMART"], m1["walmarT"])
        self.assertNotEqual(m1["WALMART"], m1["TARGET"])

    def test_no_false_merge_on_short_names(self):
        m = cluster_merchants(["UBER", "UBER EATS", "LYFT"])
        self.assertNotEqual(m["UBER"], m["LYFT"])

    def test_empty_and_single(self):
        self.assertEqual(cluster_merchants([]), {})
        self.assertEqual(cluster_merchants(["X"]), {"X": "X"})


if __name__ == "__main__":
    unittest.main()

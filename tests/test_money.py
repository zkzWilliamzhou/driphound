"""T2 tests — money.py (RED first)."""
import unittest

from driphound.errors import ParseError
from driphound.money import CURRENCY_SYMBOLS, fmt_money, parse_amount, percent_of


class TestParseAmount(unittest.TestCase):
    def test_basic_us(self):
        self.assertEqual(parse_amount("$1,234.56"), (123456, "USD"))
        self.assertEqual(parse_amount("-12.50"), (-1250, None))
        self.assertEqual(parse_amount("12.50"), (1250, None))

    def test_parentheses_and_suffixes(self):
        self.assertEqual(parse_amount("(1,250.00)"), (-125000, None))
        self.assertEqual(parse_amount("12.50 CR"), (-1250, None))
        self.assertEqual(parse_amount("12.50 CR"), parse_amount("-12.50"))
        self.assertEqual(parse_amount("12.50 DR"), (1250, None))

    def test_european_decimal_comma(self):
        self.assertEqual(parse_amount("1.234,56"), (123456, None))
        self.assertEqual(parse_amount("1234,56"), (123456, None))
        self.assertEqual(parse_amount("0,99"), (99, None))

    def test_thousands_variants(self):
        self.assertEqual(parse_amount("1 234,56"), (123456, None))
        self.assertEqual(parse_amount("1,234"), (123400, None))  # US: comma=thousands when no decimals
        self.assertEqual(parse_amount("12,34"), (1234, None))    # comma as decimal (2 digits after)
        with self.assertRaises(ParseError):                      # ambiguous: fail loudly, never guess
            parse_amount("1,2345")

    def test_currency_symbols_and_codes(self):
        self.assertEqual(parse_amount("€3.00"), (300, "EUR"))
        self.assertEqual(parse_amount("£3.00"), (300, "GBP"))
        self.assertEqual(parse_amount("USD 3.00"), (300, "USD"))
        self.assertEqual(parse_amount("3.00 USD"), (300, "USD"))
        self.assertEqual(parse_amount("¥300"), (300, "JPY"))
        self.assertEqual(parse_amount("JPY 300"), (300, "JPY"))
        self.assertIn("$", CURRENCY_SYMBOLS)

    def test_zero_decimals_currency(self):
        self.assertEqual(parse_amount("JPY 300.5"), (300, "JPY"))  # truncated with warning flag
        # round-half-even not applicable; fractional yen truncated deterministically

    def test_bad_input(self):
        for bad in ("", "   ", "abc", "12.34.56", "--5", "1e5", "$", "nan", "inf", "1,2,3.45.67"):
            with self.assertRaises(ParseError, msg=repr(bad)):
                parse_amount(bad)

    def test_big_values_no_float(self):
        cents, cur = parse_amount("99999999999999.99")
        self.assertEqual(cents, 9999999999999999)
        self.assertIsInstance(cents, int)

    def test_whitespace_and_plus(self):
        self.assertEqual(parse_amount("  +42.10 "), (4210, None))


class TestFmt(unittest.TestCase):
    def test_fmt_money(self):
        self.assertEqual(fmt_money(123456, "USD"), "$1,234.56")
        self.assertEqual(fmt_money(-123456, "USD"), "-$1,234.56")
        self.assertEqual(fmt_money(123456, None), "1,234.56")
        self.assertEqual(fmt_money(300, "JPY"), "¥300")
        self.assertEqual(fmt_money(-50, "EUR"), "-€0.50")

    def test_percent_of(self):
        self.assertEqual(percent_of(10000, 300), 3.0)     # 300c is 3% of 10000c
        self.assertEqual(percent_of(0, 300), None)
        self.assertEqual(percent_of(-10000, -300), 3.0)


if __name__ == "__main__":
    unittest.main()

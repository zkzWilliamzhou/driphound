"""Money parsing/formatting. Integer minor units only; Decimal at the edge.

Ambiguity policy (documented, deterministic):
- Both '.' and ',' present: the LAST one is the decimal separator.
- Single separator with exactly 1-2 digits after it: decimal separator.
- Single separator with exactly 3 digits after it and a valid 1-3 digit group
  before it: thousands separator (bank statements use 2-decimal money, so a
  3-digit tail is a thousands group, e.g. EU "1.234" = 1234 units).
- Repeated separators: valid only as thousands groups of exactly 3 digits.
- Anything else (e.g. "1,2345"): ParseError. We fail loudly on ambiguous money.
- Zero-decimal currencies (JPY, KRW, ...): minor unit == major unit; any
  fractional part is truncated.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation
from typing import Optional, Tuple

from .errors import ParseError

CURRENCY_SYMBOLS = {
    "$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₹": "INR", "₩": "KRW",
    "₽": "RUB", "₺": "TRY", "R$": "BRL", "kr": None,  # kr is ambiguous (SEK/NOK/DKK) -> no currency
}
CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD", "SEK", "NOK", "DKK",
    "PLN", "CZK", "HUF", "INR", "CNY", "KRW", "BRL", "MXN", "ZAR", "TRY", "RUB",
    "SGD", "HKD", "ILS", "THB", "MYR", "IDR", "PHP", "TWD", "ISK", "CLP", "COP",
    "ARS", "VND", "SAR", "AED",
}
ZERO_DECIMAL = {"JPY", "KRW", "VND", "CLP", "ISK", "HUF", "TWD"}

_SIGN_WORDS = {"CR": -1, "DB": 1, "DR": 1}
_ALLOWED = re.compile(r"^-?[\d,. \u00a0]+$")
_CODE_RE = re.compile(r"\b([A-Z]{3})\b")


def parse_amount(raw: object) -> Tuple[int, Optional[str]]:
    """Parse a money string -> (minor_units:int, currency:str|None). ParseError if ambiguous/invalid."""
    if raw is None:
        raise ParseError("empty amount")
    s = str(raw).strip().replace("\u00a0", " ")
    if not s:
        raise ParseError("empty amount")

    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1].strip()

    m = re.search(r"\b(CR|DR|DB)\b$", s, re.IGNORECASE)
    if m:
        sign = _SIGN_WORDS[m.group(1).upper()]
        if sign < 0:
            negative = True
        s = s[: m.start()].strip()

    currency: Optional[str] = None
    for sym, code in CURRENCY_SYMBOLS.items():
        if s.startswith(sym):
            currency = code
            s = s[len(sym):].strip()
            break
        if s.endswith(sym) and sym != "kr":
            currency = code
            s = s[: -len(sym)].strip()
            break
    if currency is None:
        cm = _CODE_RE.search(s)
        if cm and cm.group(1) in CURRENCY_CODES:
            currency = cm.group(1)
            s = (s[: cm.start()] + s[cm.end():]).strip()

    if s.startswith("+"):
        s = s[1:].strip()
    if s.startswith("-"):
        negative = not negative
        s = s[1:].strip()

    s = s.replace(" ", "")
    if not s or not _ALLOWED.match(s) or "e" in s.lower():
        raise ParseError("invalid amount: %r" % (raw,))
    if "-" in s or "+" in s:
        raise ParseError("invalid amount (repeated sign): %r" % (raw,))
    if not any(ch.isdigit() for ch in s):
        raise ParseError("invalid amount: %r" % (raw,))

    value = _resolve_separators(s, raw)
    try:
        d = Decimal(value)
    except InvalidOperation:
        raise ParseError("invalid amount: %r" % (raw,)) from None

    if currency in ZERO_DECIMAL:
        units = int(d.to_integral_value(rounding=ROUND_HALF_EVEN)) if d == d.to_integral_value() else int(d)
        cents = units  # minor unit == major unit; fraction truncated
    else:
        cents = int((d * 100).quantize(Decimal(1), rounding=ROUND_HALF_EVEN))
    return (-cents if negative else cents), currency


def _resolve_separators(s: str, raw: object) -> str:
    """Return a plain decimal string ('-?' digits '.' digits) from separator soup."""
    dots, commas = s.count("."), s.count(",")
    if dots and commas:
        if dots > 1 and commas > 1:
            raise ParseError("invalid amount: %r" % (raw,))
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        idx = s.rfind(dec)
        int_part, frac_part = s[:idx], s[idx + 1:]
        if not frac_part.isdigit() or not _valid_thousands(int_part, thou):
            raise ParseError("invalid amount: %r" % (raw,))
        return int_part.replace(thou, "") + "." + frac_part
    for sep in (".", ","):
        if s.count(sep) == 1:
            head, _, tail = s.partition(sep)
            if len(tail) in (1, 2):
                return head + "." + tail
            if len(tail) == 3 and 1 <= len(head.lstrip("0") or "0") <= 3 and head.isdigit():
                return head + tail  # thousands separator
            raise ParseError("ambiguous amount: %r" % (raw,))
        if s.count(sep) > 1:
            if not _valid_thousands(s, sep):
                raise ParseError("invalid amount: %r" % (raw,))
            return s.replace(sep, "")
    return s


def _valid_thousands(s: str, sep: str) -> bool:
    parts = s.split(sep)
    if len(parts) < 2:
        return False
    if not (1 <= len(parts[0]) <= 3) or not parts[0].isdigit():
        return False
    return all(len(p) == 3 and p.isdigit() for p in parts[1:])


def fmt_money(minor: int, currency: Optional[str]) -> str:
    symbol = ""
    if currency:
        for sym, code in CURRENCY_SYMBOLS.items():
            if code == currency:
                symbol = sym
                break
    neg = minor < 0
    minor = abs(minor)
    if currency in ZERO_DECIMAL:
        body = "{:,}".format(minor)
    else:
        body = "{:,}.{:02d}".format(minor // 100, minor % 100)
    return ("-" if neg else "") + symbol + body


def percent_of(base_minor: int, part_minor: int) -> Optional[float]:
    """What percent of ``base`` is ``part``? None when base == 0. Stats use float, money never does."""
    if not base_minor:
        return None
    return float((Decimal(part_minor) / Decimal(base_minor) * 100).quantize(Decimal("0.0001")))

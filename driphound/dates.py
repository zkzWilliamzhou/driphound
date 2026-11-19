"""Date parsing with explicit ambiguity handling.

Default when a 3-part numeric date is ambiguous and no order hint is given:
MDY (documented; ingest-level column inference should pass an explicit order).
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Iterable, List, Optional

from .errors import ParseError

_NUMERIC = re.compile(r"^\d+$")
_SPLIT = re.compile(r"[-/.]")
_MONTH_FORMATS = (
    "%b %d, %Y", "%B %d, %Y", "%d %b %Y", "%d %B %Y",
    "%b %d %Y", "%B %d %Y", "%d %b, %Y", "%d %B, %Y",
    "%d-%b-%y", "%d-%b-%Y", "%d-%B-%Y", "%b-%d-%y", "%b-%d-%Y", "%B-%d-%Y",
    "%d %b %y", "%b %d %y",
)


def _pivot_year(y: int) -> int:
    return 2000 + y if y < 50 else 1900 + y


def _mk(y: int, m: int, d: int, raw: object) -> date:
    try:
        return date(y, m, d)
    except ValueError:
        raise ParseError("invalid date: %r" % (raw,)) from None


def parse_date(raw: object, order: Optional[str] = None) -> date:
    """Parse one date string. ``order`` in {'MDY','DMY','YMD'} forces component order."""
    if isinstance(raw, date):
        return raw
    if raw is None:
        raise ParseError("empty date")
    s = str(raw).strip()
    if not s:
        raise ParseError("empty date")

    if _NUMERIC.match(s):
        n = len(s)
        if n == 8:  # YYYYMMDD (falls through to epoch only if not a valid compact date)
            try:
                return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))
            except ValueError:
                pass
        if n in (9, 10):
            try:
                return datetime.fromtimestamp(int(s), tz=timezone.utc).date()
            except (ValueError, OSError, OverflowError):
                raise ParseError("invalid date: %r" % (raw,)) from None
        if n in (12, 13):
            try:
                return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc).date()
            except (ValueError, OSError, OverflowError):
                raise ParseError("invalid date: %r" % (raw,)) from None
        raise ParseError("invalid date: %r" % (raw,))

    if any(ch.isalpha() for ch in s):
        for fmt in _MONTH_FORMATS:
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        raise ParseError("invalid date: %r" % (raw,))

    parts = _SPLIT.split(s)
    if len(parts) != 3 or not all(_NUMERIC.match(p) for p in parts):
        raise ParseError("invalid date: %r" % (raw,))
    a, b, c = (int(p) for p in parts)

    eff = order
    if eff is None:
        if len(parts[0]) == 4:
            eff = "YMD"
        elif len(parts[2]) == 4:
            # Check if day > 12 (DD.MM.YYYY format)
            if a > 12 and b <= 12:
                eff = "DMY"
            elif b > 12 and a <= 12:
                eff = "MDY"
            else:
                eff = "MDY"
        elif len(parts[2]) == 4:
            if a > 12 and b <= 12:
                eff = "DMY"
            elif b > 12 and a <= 12:
                eff = "MDY"
            else:
                eff = "MDY"  # documented default for ambiguous
        elif len(parts[2]) == 2:
            if a > 12 and b <= 12:
                eff = "DMY"
            elif b > 12 and a <= 12:
                eff = "MDY"
            else:
                eff = "MDY"
        else:
            raise ParseError("invalid date: %r" % (raw,))

    if eff == "YMD":
        y, m, d = a, b, c
    elif eff == "DMY":
        d, m, y = a, b, c
    else:
        m, d, y = a, b, c
    if y < 100:
        y = _pivot_year(y)
    return _mk(y, m, d, raw)


def infer_order(samples: Iterable[object]) -> Optional[str]:
    """Infer 'MDY'|'DMY'|'YMD' from a column of raw values; None if no evidence or conflicting."""
    votes: List[str] = []
    for raw in samples:
        s = str(raw or "").strip()
        parts = _SPLIT.split(s)
        if len(parts) != 3 or not all(_NUMERIC.match(p) for p in parts):
            continue
        if len(parts[0]) == 4:
            votes.append("YMD")
            continue
        if len(parts[2]) != 4:
            continue
        a, b = int(parts[0]), int(parts[1])
        if a > 12 >= b:
            votes.append("DMY")
        elif b > 12 >= a:
            votes.append("MDY")
    if not votes:
        return None
    kinds = set(votes)
    if len(kinds) != 1:
        return None
    return votes[0]

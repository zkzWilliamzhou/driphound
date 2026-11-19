"""Core domain model: Tx, Statement, Finding, Report.

Money rule (charter): integer minor units ("cents") ONLY. For zero-decimal
currencies (JPY, KRW, ...) the minor unit is the major unit. Never float.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date as _date
from typing import Dict, List, Optional, Tuple

from .errors import DripHoundError

SEVERITIES = ("info", "low", "medium", "high")
_WS = re.compile(r"\s+")


def _hash16(*parts: object) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update(repr(p).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:16]


@dataclass
class Tx:
    """One normalized transaction.

    ``date`` is stored as an ISO string (canonical, sortable); use ``as_date()``
    for date arithmetic. ``amount_cents`` is negative for debits by convention
    after sign normalization at ingest.
    """

    date: str
    amount_cents: int
    currency: Optional[str]
    merchant_raw: str
    memo: str
    account: str
    source: str
    line: int
    merchant_norm: str = ""
    balance_cents: Optional[int] = None
    category: str = ""
    id: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if isinstance(self.date, _date):
            self.date = self.date.isoformat()
        if not isinstance(self.date, str) or not self.date:
            raise TypeError("Tx.date must be a non-empty ISO string or datetime.date")
        if isinstance(self.amount_cents, bool) or not isinstance(self.amount_cents, int):
            raise TypeError("Tx.amount_cents must be int (minor units), got %r" % (self.amount_cents,))
        if self.balance_cents is not None and (
            isinstance(self.balance_cents, bool) or not isinstance(self.balance_cents, int)
        ):
            raise TypeError("Tx.balance_cents must be int or None")
        self.merchant_raw = str(self.merchant_raw)
        self.merchant_norm = self.merchant_norm or _WS.sub(" ", self.merchant_raw.strip()).lower()
        self.memo = str(self.memo or "")
        self.id = _hash16(self.date, self.amount_cents, self.currency, self.merchant_raw,
                          self.memo, self.account, self.source, self.line)

    def as_date(self) -> _date:
        return _date.fromisoformat(self.date)

    def is_debit(self) -> bool:
        return self.amount_cents < 0


@dataclass
class Statement:
    """Transactions parsed from one source file (one account/export)."""

    source: str
    format: str
    transactions: List[Tx] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    meta: Dict[str, object] = field(default_factory=dict)

    def add(self, tx: Tx) -> None:
        self.transactions.append(tx)
        if len(self.currencies()) > 1 and not any(w.startswith("mixed-currency") for w in self.warnings):
            self.warnings.append("mixed-currency: statement contains %s; totals are per-currency only"
                                 % ",".join(sorted(self.currencies())))

    def currencies(self) -> List[str]:
        return sorted({t.currency for t in self.transactions if t.currency})

    def debit_totals_by_currency(self) -> Dict[str, int]:
        out: Dict[str, int] = {}
        for t in self.transactions:
            if t.amount_cents < 0:
                key = t.currency or ""
                out[key] = out.get(key, 0) + (-t.amount_cents)
        return out

    def date_range(self) -> Tuple[str, str]:
        ds = sorted(t.date for t in self.transactions)
        return (ds[0], ds[-1]) if ds else ("", "")


@dataclass
class Finding:
    """One explainable finding. Every finding cites evidence transaction ids."""

    kind: str
    severity: str
    confidence: float
    title: str
    detail: str
    evidence: List[str]
    annualized_cents: int
    currency: Optional[str]
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    next_due: Optional[str] = None
    params: Dict[str, object] = field(default_factory=dict)
    id: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        if self.severity not in SEVERITIES:
            raise ValueError("severity must be one of %s, got %r" % (SEVERITIES, self.severity))
        if not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be within [0,1], got %r" % (self.confidence,))
        if isinstance(self.annualized_cents, bool) or not isinstance(self.annualized_cents, int):
            raise TypeError("annualized_cents must be int")
        self.confidence = round(float(self.confidence), 4)
        self.id = _hash16(self.kind, self.title, tuple(self.evidence), self.first_seen,
                          self.params.get("period_days"))


@dataclass
class Report:
    """Aggregated scan result."""

    version: str
    statements: List[Statement] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    stats: Dict[str, object] = field(default_factory=dict)
    tx_index: Dict[str, Tx] = field(default_factory=dict, compare=False)

    def index_transactions(self) -> None:
        self.tx_index = {}
        for s in self.statements:
            for t in s.transactions:
                self.tx_index[t.id] = t

    def annualized_leak_cents(self, currency: Optional[str] = None) -> int:
        present = {f.currency for f in self.findings if f.annualized_cents}
        if currency is None:
            if len(present) > 1:
                raise DripHoundError(
                    "refusing to total across currencies %s; call annualized_leak_cents(currency)"
                    % sorted(c or "?" for c in present))
            currency = next(iter(present)) if present else None
        return sum(f.annualized_cents for f in self.findings
                   if f.currency == currency and f.annualized_cents > 0)

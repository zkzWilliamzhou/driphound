"""Column mapping utilities.

Map arbitrary CSV columns to standard transaction fields.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any, Tuple

from ..errors import MappingError


@dataclass
class ColumnMapping:
    """Mapping between CSV columns and transaction fields."""
    
    date: Optional[int] = None
    amount: Optional[int] = None
    merchant: Optional[int] = None
    memo: Optional[int] = None
    account: Optional[int] = None
    currency: Optional[int] = None
    balance: Optional[int] = None
    debit: Optional[int] = None
    credit: Optional[int] = None
    
    # Additional custom mappings
    extras: Dict[str, str] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> "ColumnMapping":
        """Create ColumnMapping from dictionary."""
        return cls(
            date=data.get("date", "date"),
            amount=data.get("amount", "amount"),
            merchant=data.get("merchant", "merchant"),
            memo=data.get("memo", "memo"),
            account=data.get("account", "account"),
            currency=data.get("currency", "currency"),
            balance=data.get("balance"),
            debit=data.get("debit"),
            credit=data.get("credit"),
            extras=data.get("extras", {}),
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "date": self.date,
            "amount": self.amount,
            "merchant": self.merchant,
            "memo": self.memo,
            "account": self.account,
            "currency": self.currency,
        }
        if self.balance is not None:
            result["balance"] = self.balance
        if self.debit is not None:
            result["debit"] = self.debit
        if self.credit is not None:
            result["credit"] = self.credit
        if self.extras:
            result["extras"] = self.extras
        return result
    
    def to_file(self, path: str) -> None:
        """Save mapping to JSON file."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    @classmethod
    def from_file(cls, path: str) -> "ColumnMapping":
        """Load mapping from JSON file."""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


@dataclass
class MappingProfile:
    """A persistent mapping profile for a data source."""
    
    source: str
    mapping: ColumnMapping
    notes: str = ""
    created: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MappingProfile":
        """Create MappingProfile from dictionary."""
        return cls(
            source=data.get("source", "unknown"),
            mapping=ColumnMapping.from_dict(data.get("mapping", {})),
            notes=data.get("notes", ""),
            created=data.get("created", ""),
            extra=data.get("extra", {}),
        )
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "source": self.source,
            "mapping": self.mapping.to_dict(),
            "notes": self.notes,
            "created": self.created,
            "extra": self.extra,
        }


def infer_columns(
    headers: List[str],
    rows: List[List[str]] | None = None,
    source: str = "unknown",
    confidence_threshold: float = 0.6,
) -> ColumnMapping:
    """
    Infer column mapping from CSV headers and optional sample rows.
    
    Args:
        headers: List of CSV header names
        rows: Optional sample rows for content-based inference
        source: Source identifier for the profile
        confidence_threshold: Minimum confidence for auto-mapping
    
    Returns:
        ColumnMapping with inferred column indices or names
    """
    mapping = ColumnMapping()
    
    if not headers and not rows:
        raise MappingError("No headers provided")
    
    headers_lower = [h.lower().strip() for h in headers]
    
    # Define common patterns for each field
    field_patterns = {
        "date": ["date", "transaction date", "posted date", "date posted", "tx date", "date (yyyy-mm-dd)", "datum", "datum (yyyy-mm-dd)"],
        "amount": ["amount", "amt", "total", "value", "tx amount", "debit", "credit", "$", "betrag", "wert"],
        "merchant": ["merchant", "vendor", "payee", "description", "name", "party", "from", "to", "who", "store", "beschreibung", "bezeichnung"],
        "memo": ["memo", "notes", "note", "detail", "category", "info"],
        "account": ["account", "acct", "acct #", "card", "bank", "source"],
        "currency": ["currency", "ccy", "sym", "$", "€", "£", "¥", "currency code"],
        "balance": ["balance", "bal", "running balance"],
        "debit": ["debit", "dr", "soll"],
        "credit": ["credit", "cr", "haben"],
    }
    
    # First pass: header-based inference
    for field, patterns in field_patterns.items():
        for pattern in patterns:
            if pattern in headers_lower:
                idx = headers_lower.index(pattern)
                if field == "date":
                    mapping.date = idx
                elif field == "amount":
                    mapping.amount = idx
                elif field == "merchant":
                    mapping.merchant = idx
                elif field == "memo":
                    mapping.memo = idx
                elif field == "account":
                    mapping.account = idx
                elif field == "currency":
                    mapping.currency = idx
                elif field == "balance":
                    mapping.balance = idx
                elif field == "debit":
                    mapping.debit = idx
                elif field == "credit":
                    mapping.credit = idx
                break
    
    # Second pass: content-based inference for missing fields
    if rows:
        for field in ["date", "amount", "merchant"]:
            # Check if field was already set in first pass (not None)
            if getattr(mapping, field) is not None:  # Already set in first pass
                continue
            
            for row_idx, row in enumerate(rows[:5]):  # Check first 5 rows
                for col_idx, cell in enumerate(row):
                    cell_lower = cell.lower().strip() if cell else ""
                    
                    # Date detection
                    if field == "date" and (
                        re_search(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", cell_lower) or
                        re_search(r"\d{4}[/-]\d{1,2}[/-]\d{1,2}", cell_lower)
                    ):
                        mapping.date = col_idx
                    
                    # Amount detection
                    if field == "amount" and (
                        re.search(r"-?\d+\.\d{2}", cell_lower) or
                        re.search(r"\d+\.\d{2}", cell_lower)
                    ):
                        mapping.amount = col_idx
                    
                    # Merchant detection (cell that's neither date nor amount)
                    if field == "merchant" and col_idx not in [mapping.date, mapping.amount]:
                        # Also check if it doesn't look like an amount
                        is_amount = re.search(r"-?\d+\.\d{2}", cell_lower) or re.search(r"\d+\.\d{2}", cell_lower)
                        if cell_lower and not any(x in cell_lower for x in ["date", "amount", "$"]) and not is_amount:
                            mapping.merchant = col_idx
    
    # Validate critical fields - raise error if essential fields couldn't be inferred
    if mapping.date is None and rows:
        # Try to find a date column from content
        for col_idx in range(len(headers)):
            if col_idx < len(rows[0]):
                from ..dates import parse_date
                try:
                    parse_date(rows[0][col_idx])
                    mapping.date = col_idx
                    break
                except:
                    pass
    
    # After all inference attempts, check if essential fields were found
    if mapping.date is None:
        raise MappingError(f"Could not infer 'date' column from headers {headers}")
    if mapping.amount is None:
        raise MappingError(f"Could not infer 'amount' column from headers {headers}")
    if mapping.merchant is None:
        raise MappingError(f"Could not infer 'merchant' column from headers {headers}")
    
    return mapping


def re_search(pattern: str, string: str) -> Any:
    """Helper to use re module without import in outer scope."""
    import re
    return re.search(pattern, string, re.IGNORECASE)


def delete_profile(name: str, directory: str) -> None:
    """Delete a mapping profile file."""
    profile_path = os.path.join(directory, f"{name}.json")
    if os.path.exists(profile_path):
        os.remove(profile_path)


def list_profiles(directory: str) -> List[str]:
    """List all mapping profiles in a directory."""
    if not os.path.exists(directory):
        return []
    profiles = []
    for f in os.listdir(directory):
        if f.endswith(".json"):
            profiles.append(f[:-5])  # Remove .json extension
    return sorted(profiles)


def load_profile(name: str, directory: str) -> Tuple[ColumnMapping, Dict[str, Any]]:
    """Load a mapping profile from a file.
    
    Returns tuple of (ColumnMapping, extra dict).
    """
    profile_path = os.path.join(directory, f"{name}.json")
    if not os.path.exists(profile_path):
        raise MappingError(f"Profile '{name}' not found in {directory}")
    
    with open(profile_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    mapping = ColumnMapping.from_dict(data.get("mapping", data))
    extra = data.get("extra", {})
    
    return mapping, extra


def save_profile(
    name: str,
    mapping: ColumnMapping,
    directory: str,
    extra: Optional[Dict[str, Any]] = None,
) -> str:
    """Save a mapping profile to a file.
    
    Args:
        name: Profile name
        mapping: ColumnMapping to save
        directory: Directory to save to
        extra: Optional extra metadata
    
    Returns:
        Path to saved file
    """
    # Security check: prevent path traversal
    if ".." in name or "/" in name or "\\" in name:
        raise MappingError(f"Invalid profile name: {name}")
    
    os.makedirs(directory, exist_ok=True)
    profile_path = os.path.join(directory, f"{name}.json")
    
    data = mapping.to_dict()
    if extra:
        data["extra"] = extra
    
    with open(profile_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    
    return profile_path


def get_profile(source: str, profile_dir: str = "~/.driphound/mappings") -> Optional[ColumnMapping]:
    """Load a saved mapping profile for a source (returns just the mapping, no extra)."""
    profile_path = os.path.expanduser(f"{profile_dir}/{source}.json")
    if os.path.exists(profile_path):
        return ColumnMapping.from_file(profile_path)
    return None


def apply_mapping(
    row: Dict[str, str],
    mapping: ColumnMapping,
) -> Dict[str, Any]:
    """Apply a column mapping to a CSV row."""
    result = {}
    
    def get_col(col_name: str) -> str:
        """Get column value, handling index-based columns."""
        val = row.get(col_name, "")
        # If it's a numeric string, treat as index
        if col_name.isdigit():
            cols = list(row.values())
            if int(col_name) < len(cols):
                return cols[int(col_name)]
        return val
    
    # Map standard fields
    result["date"] = get_col(mapping.date)
    result["merchant_raw"] = get_col(mapping.merchant)
    result["memo"] = get_col(mapping.memo) or ""
    result["account"] = get_col(mapping.account)
    result["currency"] = get_col(mapping.currency).upper() or None
    
    if mapping.balance:
        result["balance"] = get_col(mapping.balance)
    if mapping.debit:
        result["debit"] = get_col(mapping.debit)
    if mapping.credit:
        result["credit"] = get_col(mapping.credit)
    
    # Map amount (special handling for sign)
    amount_str = get_col(mapping.amount)
    result["amount_raw"] = amount_str
    
    return result


class MappingSuggestion:
    """A suggestion for column mapping with confidence score."""
    
    def __init__(self, field: str, column: str, confidence: float):
        self.field = field
        self.column = column
        self.confidence = confidence
    
    def to_dict(self) -> dict:
        return {
            "field": self.field,
            "column": self.column,
            "confidence": self.confidence,
        }
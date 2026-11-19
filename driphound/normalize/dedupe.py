"""Deduplication utilities.

Identify and remove duplicate transactions.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Dict, Set, Tuple, Callable, Optional
from .merchant import MerchantNormalizer

from ..model import Tx, Statement


def tx_key(
    tx: Tx,
    fields: Optional[List[str]] = None,
    normalize_merchant: bool = True,
) -> str:
    """
    Generate a deduplication key for a transaction.
    
    The key is based on date, amount, and merchant (optionally normalized).
    Two transactions with the same key are considered duplicates.
    
    Args:
        tx: Transaction to key
        fields: Specific fields to include (default: date, amount, merchant)
        normalize_merchant: Whether to normalize merchant name
    
    Returns:
        Hash key string
    """
    if fields is None:
        fields = ["date", "amount_cents", "merchant_norm"]
    
    key_parts = []
    for f in fields:
        if f == "merchant_norm" and normalize_merchant:
            # Use normalized merchant
            from .merchant import alias_of, clean_merchant
            key_parts.append(clean_merchant(tx.merchant_raw))
        else:
            key_parts.append(str(getattr(tx, f, "")))
    
    key_str = "|".join(key_parts)
    return hashlib.sha256(key_str.encode("utf-8")).hexdigest()[:16]


def dedupe(
    statement: Union[Statement, List[Tx]],
    key_func: Optional[Callable[[Tx], str]] = None,
    keep_first: bool = True,
) -> Union[Tuple[Statement, List[Tx]], Tuple[List[Tx], List[Tx]]]:
    """
    Remove duplicate transactions from a statement or list of transactions.
    
    Args:
        statement: Input Statement or list of Tx objects
        key_func: Custom function to generate deduplication keys
        keep_first: If True, keep first occurrence; if False, keep last
    
    Returns:
        If input is Statement: Tuple of (deduplicated Statement, list of removed duplicates)
        If input is List[Tx]: Tuple of (kept list, removed list)
    """
    if key_func is None:
        key_func = tx_key
    
    # Handle list input
    is_list_input = isinstance(statement, list)
    if is_list_input:
        txs = list(statement)
    else:
        txs = list(statement.transactions)
    
    seen: Dict[str, Tx] = {}
    duplicates: List[Tx] = []
    
    if not keep_first:
        txs = list(reversed(txs))
    
    for tx in txs:
        key = key_func(tx)
        if key in seen:
            duplicates.append(tx)
        else:
            seen[key] = tx
    
    if not keep_first:
        # Reverse order to maintain chronological
        seen = dict(list(seen.items())[::-1])
    
    if is_list_input:
        return list(seen.values()), duplicates
    
    # Create new statement with deduplicated transactions
    new_stmt = Statement(
        source=statement.source,
        format=statement.format,
        meta=statement.meta.copy(),
    )
    new_stmt.transactions = list(seen.values())
    new_stmt.warnings = statement.warnings + [f"Removed {len(duplicates)} duplicates"]
    
    return new_stmt, duplicates


def find_duplicates(
    txs: List[Tx],
    tolerance_seconds: int = 300,  # 5 minutes
) -> List[List[Tx]]:
    """
    Find groups of potential duplicate transactions.
    
    Transactions within tolerance_seconds of each other with same amount
    and similar merchant are considered potential duplicates.
    """
    groups: List[List[Tx]] = []
    used: Set[int] = set()
    
    for i, tx1 in enumerate(txs):
        if i in used:
            continue
        
        group = [tx1]
        for j, tx2 in enumerate(txs[i+1:], start=i+1):
            if j in used:
                continue
            
            # Same amount (within cent tolerance)
            if abs(tx1.amount_cents - tx2.amount_cents) > 1:
                continue
            
            # Same date (within tolerance)
            try:
                from datetime import datetime
                d1 = datetime.fromisoformat(tx1.date)
                d2 = datetime.fromisoformat(tx2.date)
                if abs((d2 - d1).total_seconds()) > tolerance_seconds:
                    continue
            except (ValueError, TypeError):
                continue
            
            # Similar merchant (case-insensitive, ignoring small differences)
            m1 = tx1.merchant_norm.lower().strip()
            m2 = tx2.merchant_norm.lower().strip()
            if abs(len(m1) - len(m2)) > 5:  # Very different lengths
                continue
            
            # If we get here, consider it a potential duplicate
            group.append(tx2)
            used.add(j)
        
        if len(group) > 1:
            groups.append(group)
            used.add(i)
    
    return groups
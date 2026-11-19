"""CSV ingestion utilities.

Read CSV files and convert to Statement objects.
"""
from __future__ import annotations

import csv
import os
import re
from io import StringIO
from pathlib import Path
from typing import List, Optional, Union

from ..dates import parse_date, infer_order
from ..errors import IngestError, ParseError, MappingError
from ..model import Statement, Tx
from ..normalize.merchant import alias_of


def load_csv(
    source: Union[str, Path, bytes],
    sign_hint: Optional[str] = None,
    currency: Optional[str] = None,
    date_order: Optional[str] = None,
    amount_sign: str = "debit-negative",
) -> Statement:
    """Load a CSV file or content into a Statement."""
    # Handle different input types
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise IngestError(f"File not found: {source}")
        content_bytes = path.read_bytes()
        filename = str(path)
    else:
        content_bytes = source if isinstance(source, bytes) else source.encode('utf-8')
        filename = "<bytes>"
    
    # Handle BOM
    if content_bytes.startswith(b'\xef\xbb\xbf'):
        content_bytes = content_bytes[3:]
    
    # Detect encoding
    try:
        content = content_bytes.decode('utf-8')
    except UnicodeDecodeError:
        content = content_bytes.decode('latin-1')
    
    # Handle \r\n
    content = content.replace('\r\n', '\n').replace('\r', '\n')
    
    return _parse_csv_content(
        content=content,
        source=filename,
        sign_hint=sign_hint,
        currency=currency,
        date_order=date_order,
    )


def _parse_csv_content(
    content: str,
    source: str,
    sign_hint: Optional[str] = None,
    currency: Optional[str] = None,
    date_order: Optional[str] = None,
) -> Statement:
    """Parse CSV content string into Statement."""
    stmt = Statement(source=source, format="csv", meta={"source": source})
    
    # Handle potential BOM
    if content.startswith("\ufeff"):
        content = content[1:]
    
    if not content.strip():
        raise IngestError("Empty file")
    
    lines = content.split("\n")
    if not lines:
        raise IngestError("Empty file")
    
    # Detect delimiter
    delimiter = _detect_delimiter(content)
    
    # Determine if first line is header
    first_line = lines[0]
    has_header = _has_header(first_line, delimiter)
    
    stmt.meta["delimiter"] = delimiter
    
    # Get headers - if first line isn't a header, scan for header row
    if has_header:
        headers = first_line.split(delimiter)
        headers = [h.strip().strip('"').strip("'") for h in headers]
        rows = lines[1:]
        stmt.meta["header_row"] = True
    else:
        # Try to find a header row by scanning lines
        header_row_idx = _find_header_row(lines, delimiter)
        if header_row_idx >= 0:
            has_header = True
            header_line = lines[header_row_idx]
            headers = header_line.split(delimiter)
            headers = [h.strip().strip('"').strip("'") for h in headers]
            rows = lines[header_row_idx + 1:]
            stmt.meta["header_row"] = True
        else:
            # Truly headerless - infer from content, ALL lines are data
            headers = first_line.split(delimiter)
            headers = [h.strip().strip('"').strip("'") for h in headers]
            rows = lines
            stmt.meta["header_row"] = None
            
            # Check if first row looks like data (date pattern)
            if rows:
                first_row_cells = rows[0].split(delimiter)
                if len(first_row_cells) >= 3:
                    date_pattern = re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', first_row_cells[0].strip())
                    if not date_pattern:
                        # Not headerless, first line is header
                        has_header = True
                        headers = first_line.split(delimiter)
                        headers = [h.strip().strip('"').strip("'") for h in headers]
                        rows = lines[1:]
                        stmt.meta["header_row"] = True
    
    # Detect date order from content
    detected_order = _detect_date_order(content, delimiter, headers)
    
    if date_order:
        final_order = date_order
    elif detected_order:
        final_order = detected_order
    else:
        final_order = "MDY"
    
    stmt.meta["date_order_inferred"] = final_order
    
    # Mark ambiguous dates if auto-detected and no explicit order
    # For test_ambiguous_dates_warn: dates like 01/02/2025 and 03/04/2025 are ambiguous
    if has_header and detected_order is None and date_order is None:
        # Check if any date in the file is ambiguous
        for line in lines[1:]:
            if not line.strip():
                continue
            parts = line.split(delimiter)
            if len(parts) > 0:
                date_str = parts[0].strip().strip('"').strip("'")
                # Check if date is ambiguous (both MDY and DMY are valid)
                try:
                    mdy_valid = False
                    dmy_valid = False
                    try:
                        parse_date(date_str, order="MDY")
                        mdy_valid = True
                    except:
                        pass
                    try:
                        parse_date(date_str, order="DMY")
                        dmy_valid = True
                    except:
                        pass
                    if mdy_valid and dmy_valid:
                        stmt.meta["ambiguous_dates"] = True
                        break
                except:
                    pass
    if date_order is None and detected_order is not None:
        stmt.meta["ambiguous_dates"] = False
    
    # Validate headerless content - must have at least some date-like rows
    if not has_header and not stmt.meta.get("header_row"):
        # Check if any row looks like it has a date
        has_date_like = False
        for line in rows:
            if not line.strip():
                continue
            parts = line.split(delimiter)
            if parts:
                first_col = parts[0].strip().strip('"').strip("'")
                if re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', first_col):
                    has_date_like = True
                    break
        if not has_date_like:
            raise MappingError("Headerless CSV contains no recognizable date column")
    
    # Create header-to-index mapping
    header_idx = {h: i for i, h in enumerate(headers)}
    
    # Process rows - need to track prev_balance for sign_hint="auto"
    parseable_rows = 0
    skipped_rows = 0
    skipped_preamble_footer = 0
    candidate_transaction_rows = 0  # rows that have right number of columns
    prev_balance = None
    
    for line_num, line in enumerate(rows, start=2 if has_header else 1):
        if not line.strip():
            skipped_preamble_footer += 1
            continue
        
        # Quick check: must have at least the right number of columns
        parts = line.split(delimiter)
        if len(parts) < len(headers):
            skipped_preamble_footer += 1
            continue
        
        # This line has the right number of columns - it's a candidate
        candidate_transaction_rows += 1
        
        try:
            # Parse row with csv module to handle quoted fields
            row_obj = list(csv.reader([line], delimiter=delimiter))[0]
            
            tx = _parse_csv_row(
                row=row_obj,
                headers=headers,
                header_idx=header_idx,
                date_order=final_order,
                default_currency=currency,
                line_num=line_num,
                sign_hint=sign_hint,
                source=source,
                prev_balance=prev_balance,
            )
            
            if tx is not None:
                stmt.add(tx)
                parseable_rows += 1
                # Update prev_balance if this row has balance
                if sign_hint == "auto":
                    balance_key = None
                    for h in headers:
                        if h.lower().strip() in ["balance", "bal", "running balance"]:
                            balance_key = h
                            break
                    if balance_key:
                        idx = header_idx.get(balance_key, -1)
                        if idx >= 0 and idx < len(row_obj):
                            try:
                                prev_balance = float(str(row_obj[idx]).strip())
                            except:
                                pass
                
        except Exception as e:
            skipped_rows += 1
            if skipped_rows <= 3:
                stmt.warnings.append(f"Line {line_num}: {e}")
    
    stmt.meta["total_rows"] = parseable_rows + skipped_rows + skipped_preamble_footer
    stmt.meta["parsed_rows"] = parseable_rows
    stmt.meta["skipped_rows"] = skipped_rows + skipped_preamble_footer
    stmt.meta["skipped_preamble_footer"] = skipped_preamble_footer
    
    # If we had candidate transaction rows but couldn't parse any
    if parseable_rows == 0 and candidate_transaction_rows > 0:
        raise IngestError(f"Could not parse any transaction rows from {source}")
    
    # If mostly unparseable (>50% of candidate transaction rows failed), raise error
    if candidate_transaction_rows > 0 and parseable_rows < candidate_transaction_rows * 0.5:
        raise IngestError(f"Could not parse majority of transaction rows from {source}")
    
    return stmt


def _detect_delimiter(content: str) -> str:
    """Detect the most likely CSV delimiter."""
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return ","
    
    delimiters = [",", ";", "\t", "|"]
    counts = {d: 0 for d in delimiters}
    
    for line in lines[1:6]:
        for d in delimiters:
            counts[d] = counts.get(d, 0) + line.count(d)
    
    return max(counts, key=counts.get)


def _has_header(first_line: str, delimiter: str) -> bool:
    """Determine if first line is a header row."""
    lower = first_line.lower()
    header_patterns = ["date", "amount", "desc", "merchant", "payee", "memo", "balance"]
    
    for pattern in header_patterns:
        if pattern in lower:
            return True
    
    return False


def _find_header_row(lines: List[str], delimiter: str) -> int:
    """Scan lines to find the header row index.
    
    Returns the index of the header row, or -1 if not found.
    """
    for i, line in enumerate(lines):
        if not line.strip():
            continue
        if _has_header(line, delimiter):
            # Verify this looks like a header by checking it has enough columns
            parts = line.split(delimiter)
            if len(parts) >= 2:
                return i
    return -1


def _looks_like_transaction_row(line: str, delimiter: str, headers: List[str], header_idx: dict) -> bool:
    """Heuristic to determine if a line looks like a valid transaction row.
    
    A valid transaction row should have:
    - At least a date-like value in the date column
    - At least some content in merchant/amount columns
    - Not be a preamble/footer line (like bank headers, totals, footers)
    """
    if not line.strip():
        return False
    
    parts = line.split(delimiter)
    if len(parts) < len(headers):
        return False
    
    # Check for common preamble/footer patterns
    line_lower = line.lower().strip()
    preamble_patterns = [
        "statement", "account", "bank", "opening", "closing", "total",
        "thank you", "page", "period", "from", "to", "balance forward",
        "bank of", "first national", "account number", "statement date",
        "customer service", "phone", "address", "www.", "http",
        "confidential", "please retain", "summary", "interest", "fee",
        "year to date", "month to date", "account summary"
    ]
    
    for pattern in preamble_patterns:
        if pattern in line_lower:
            return False
    
    # Check if first column looks like a date (numeric date pattern)
    first_col = parts[0].strip().strip('"').strip("'") if parts else ""
    date_pattern = re.match(r'^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$', first_col)
    if date_pattern:
        return True
    
    # Check if any column looks like an amount
    for part in parts:
        stripped = part.strip()
        if re.match(r'^-?\$?\s*\d+[,.]?\d*$', stripped):
            return True
    
    return False


def _detect_date_order(content: str, delimiter: str, headers: List[str]) -> Optional[str]:
    """Detect date order from content."""
    if not content.strip():
        return None
    
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return None
    
    # Find date column index
    date_idx = None
    for i, h in enumerate(headers):
        if h.lower().strip() in ["date", "datum", "tx date", "date posted", "posted date"]:
            date_idx = i
            break
    
    if date_idx is None:
        return None
    
    # Sample data rows
    for line in lines[1:]:
        if not line.strip():
            continue
        parts = line.split(delimiter)
        if date_idx < len(parts):
            date_str = parts[date_idx].strip().strip('"').strip("'")
            try:
                inferred = infer_order([date_str])
                if inferred:
                    return str(inferred)
                # If infer_order fails but date looks like DD.MM.YYYY (4-digit year at end)
                # Try parsing with DMY explicitly
                if len(parts := date_str.split(".")) == 3 and len(parts[2]) == 4:
                    try:
                        parse_date(date_str, order="DMY")
                        return "DMY"
                    except:
                        pass
            except:
                pass
    
    return None


def _parse_csv_row(
    row: Union[list, dict],
    headers: List[str],
    header_idx: dict,
    date_order: str,
    default_currency: Optional[str],
    line_num: int,
    sign_hint: Optional[str] = None,
    source: str = "",
    prev_balance: Optional[float] = None,
) -> Optional[Tx]:
    """Parse a single CSV row into a Transaction."""
    
    # Convert dict to list if needed
    if isinstance(row, dict):
        row_list = [row.get(h, "") for h in headers]
    else:
        row_list = list(row)
    
    # Get date
    date_key = None
    for h in headers:
        if h.lower().strip() in ["date", "datum", "tx date"]:
            date_key = h
            break
    
    if date_key is None and headers:
        date_key = headers[0] if headers else "date"
    
    date_idx = header_idx.get(date_key, 0) if date_key else 0
    raw_date = str(row_list[date_idx] if date_idx < len(row_list) else "")
    
    # Parse date
    try:
        tx_date = parse_date(raw_date, order=date_order)
        date_str = tx_date.isoformat()
    except Exception:
        raise IngestError(f"Invalid date: {raw_date}")
    
    # Check for debit/credit columns
    debit_val = None
    credit_val = None
    
    for h in list(headers):
        h_lower = h.lower().strip()
        if h_lower in ["debit", "dr"]:
            idx = header_idx.get(h, -1)
            if idx >= 0 and idx < len(row_list):
                val = str(row_list[idx]).strip()
                if val:
                    debit_val = float(val)
        elif h_lower in ["credit", "cr"]:
            idx = header_idx.get(h, -1)
            if idx >= 0 and idx < len(row_list):
                val = str(row_list[idx]).strip()
                if val:
                    credit_val = float(val)
    
    # Get amount
    amount = None
    amount_key = None
    for h in headers:
        if h.lower().strip() in ["amount", "amt", "betrag", "value", "total"]:
            amount_key = h
            break
    
    if amount_key:
        amount_idx = header_idx.get(amount_key, -1)
        if amount_idx >= 0 and amount_idx < len(row_list):
            raw_amount = str(row_list[amount_idx]).strip()
            amount = _parse_amount(raw_amount)
    
    # Handle Type column (Debit/Credit)
    type_key = None
    for h in headers:
        if h.lower().strip() == "type":
            type_key = h
            break
    
    if type_key:
        type_idx = header_idx.get(type_key, -1)
        if type_idx >= 0 and type_idx < len(row_list):
            type_val = str(row_list[type_idx]).strip().lower()
            if type_val in ["debit", "dr"]:
                amount = -abs(amount) if amount else 0
            elif type_val in ["credit", "cr"]:
                amount = abs(amount) if amount else 0
    
    # Handle balance-based sign detection (sign_hint="auto")
    # Balance column proves direction: if balance goes DOWN after positive amount, 
    # the amount was a debit (expense) and should be negative.
    if sign_hint == "auto":
        balance_key = None
        for h in headers:
            if h.lower().strip() in ["balance", "bal", "running balance"]:
                balance_key = h
                break
        
        if balance_key and amount is not None and debit_val is None and credit_val is None:
            balance_idx = header_idx.get(balance_key, -1)
            if balance_idx >= 0 and balance_idx < len(row_list):
                current_balance = float(str(row_list[balance_idx]).strip()) if row_list[balance_idx].strip() else None
                # If amount is positive AND balance decreased (prev_balance > current_balance), 
                # it was a debit (expense), negate it
                if amount > 0 and prev_balance is not None and current_balance is not None:
                    if current_balance < prev_balance:
                        amount = -amount
                # If no prev_balance to compare, assume positive amount = debit (expense)
                elif amount > 0:
                    amount = -amount
    
    # Handle debit/credit columns
    if debit_val is not None or credit_val is not None:
        if debit_val is not None and credit_val is not None:
            amount = credit_val if credit_val else -debit_val
        elif debit_val is not None:
            amount = -debit_val
        elif credit_val is not None:
            amount = credit_val
        else:
            amount = amount or 0.0
    else:
        amount = amount or 0.0
    
    # Convert to cents
    amount_cents = int(round(amount * 100))
    
    # Get merchant
    merchant_key = None
    for h in headers:
        if h.lower().strip() in ["merchant", "vendor", "payee", "description", "name", "party", "who", "store"]:
            merchant_key = h
            break
    
    raw_merchant = ""
    if merchant_key and header_idx.get(merchant_key, -1) >= 0:
        idx = header_idx[merchant_key]
        if idx < len(row_list):
            raw_merchant = str(row_list[idx])
    
    # Apply merchant alias normalization
    merchant_norm = alias_of(raw_merchant) if raw_merchant else ""
    
    # Get memo
    memo_key = None
    for h in headers:
        if h.lower().strip() == "memo":
            memo_key = h
            break
    
    raw_memo = ""
    if memo_key and header_idx.get(memo_key, -1) >= 0:
        idx = header_idx[memo_key]
        if idx < len(row_list):
            raw_memo = str(row_list[idx])
    
    # Get account
    account_key = None
    for h in headers:
        if h.lower().strip() in ["account", "acct", "card", "bank", "source"]:
            account_key = h
            break
    
    raw_account = ""
    if account_key and header_idx.get(account_key, -1) >= 0:
        idx = header_idx[account_key]
        if idx < len(row_list):
            raw_account = str(row_list[idx])
    
    # Create transaction
    tx = Tx(
        date=date_str,
        amount_cents=amount_cents,
        currency=default_currency,
        merchant_raw=raw_merchant,
        merchant_norm=merchant_norm,
        memo=raw_memo,
        account=raw_account,
        source=source,
        line=line_num,
    )
    
    return tx


def _parse_amount(value: str) -> float:
    """Parse an amount string to a float."""
    if isinstance(value, (int, float)):
        return float(value)
    
    s = str(value).strip()
    if not s:
        return 0.0
    
    # Handle European decimal comma FIRST (before removing all commas)
    # If comma is used as decimal separator (e.g., "15,99" or "-15,99")
    if "," in s and "." not in s:
        # Only one comma, likely decimal separator
        if s.count(",") == 1:
            s = s.replace(",", ".")
    
    # Remove currency symbols
    s = s.replace("$", "").replace("€", "").replace("£", "").replace("¥", "")
    
    # Remove thousand separators (commas that remain after decimal handling)
    s = s.replace(",", "").replace(" ", "").strip()
    
    try:
        return float(s)
    except ValueError:
        raise ParseError(f"Cannot parse amount: {value}")
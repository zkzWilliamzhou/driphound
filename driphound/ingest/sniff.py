"""File detection utilities.

Detect file encoding and format from raw content.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple, Union


def detect_encoding(content: Union[bytes, str]) -> Tuple[str, bool]:
    """
    Detect the encoding of file content.
    
    Returns a tuple (encoding, was_guessed).
    """
    if isinstance(content, str):
        return ("utf-8", False)
    
    # Check for BOM
    if content.startswith(b'\xef\xbb\xbf'):
        return ("utf-8-sig", False)
    
    # Try UTF-8 first
    try:
        content.decode("utf-8")
        return ("utf-8", False)
    except UnicodeDecodeError:
        pass
    
    # Try common encodings
    encodings_to_try = ["utf-16", "utf-32", "utf-16-be", "utf-16-le", "cp1252", "latin-1"]
    for enc in encodings_to_try:
        try:
            content.decode(enc)
            return (enc, True)
        except (UnicodeDecodeError, LookupError):
            continue
    
    # Fallback to latin-1 (accepts all byte values)
    return ("latin-1", True)


def detect_format(content: Union[str, bytes]) -> str:
    """
    Detect the format of file content.
    
    Returns a format string: "csv", "xlsx", "qbo", "qfx", "ofx", "json", "unknown"
    """
    if isinstance(content, bytes):
        encoding, _ = detect_encoding(content)
        try:
            content = content.decode(encoding)
        except:
            content = content.decode('utf-8', errors='replace')
    
    # Remove BOM if present
    if content.startswith("\ufeff"):
        content = content[1:]
    
    content_stripped = content.strip()
    
    if not content_stripped:
        return "csv"
    
    # Check for JSON
    if content_stripped.startswith("{") or content_stripped.startswith("["):
        try:
            import json
            json.loads(content_stripped[:1000])
            return "json"
        except json.JSONDecodeError:
            pass
    
    # Check for OFX/QFX/QBO (XML-based) - also handle OFXHEADER:100 format
    lower_content = content_stripped.lower()
    upper_content = content_stripped.upper()
    if lower_content.startswith("<?xml") or lower_content.startswith("<ofx") or content_stripped.startswith("OFXHEADER"):
        if "<QFX>" in upper_content or (content_stripped.upper().startswith("OFXHEADER") and "<QFX>" in upper_content):
            return "qfx"
        if "<QBO>" in upper_content:
            return "qbo"
        if "<OFX>" in upper_content or content_stripped.startswith("OFXHEADER"):
            return "ofx"
    
    # Check for Excel-like content (very basic heuristic)
    if content_stripped.startswith("PK\x03\x04"):
        return "xlsx"
    
    # Check for CSV by looking for delimiter patterns
    lines = content_stripped.split("\n")[:5]
    if len(lines) >= 2:
        comma_count = sum(line.count(",") for line in lines)
        semicolon_count = sum(line.count(";") for line in lines)
        tab_count = sum(line.count("\t") for line in lines)
        
        max_count = max(comma_count, semicolon_count, tab_count)
        if max_count > 0 and max_count >= (len(lines) - 1):
            if comma_count >= semicolon_count and comma_count >= tab_count:
                return "csv"
    
    return "csv"


def sniff_file(content: Union[bytes, str], filename: Optional[str] = None) -> dict:
    """
    Perform full file analysis and return format info.
    """
    if isinstance(content, bytes):
        encoding, guessed = detect_encoding(content)
        text = content.decode(encoding, errors="replace")
    else:
        encoding, guessed = detect_encoding(content)
        text = content
    
    fmt = detect_format(text)
    delimiter = None
    has_header = False
    
    if fmt == "csv":
        delimiter = _detect_delimiter(text)
        has_header = _has_header_row(text, delimiter)
    
    return {
        "encoding": encoding,
        "format": fmt,
        "delimiter": delimiter,
        "has_header": has_header,
    }


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


def _has_header_row(content: str, delimiter: str) -> bool:
    """Heuristic to detect if first row is a header."""
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return True
    
    first_row = lines[0].strip()
    second_row = lines[1].strip()
    
    # Check if first row contains typical header patterns
    header_patterns = ["date", "amount", "desc", "merchant", "payee", "memo", "category"]
    first_lower = first_row.lower()
    
    for pattern in header_patterns:
        if pattern in first_lower:
            return True
    
    # Check if first row has no numbers (headers typically have no numbers)
    first_has_number = bool(re.search(r"\d", first_row))
    second_has_number = bool(re.search(r"\d", second_row))
    
    if not first_has_number and second_has_number:
        return True
    
    return False
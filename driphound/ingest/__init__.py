"""DripHound ingestion module.

Ingest CSV, bank exports, and other financial data formats.
"""
from .csving import load_csv
from .sniff import detect_encoding, detect_format, sniff_file
from .mapping import (
    ColumnMapping,
    MappingProfile,
    infer_columns,
    delete_profile,
    get_profile,
    save_profile,
    apply_mapping,
)

__all__ = [
    "load_csv",
    "detect_encoding",
    "detect_format",
    "sniff_file",
    "ColumnMapping",
    "MappingProfile",
    "infer_columns",
    "delete_profile",
    "get_profile",
    "save_profile",
    "apply_mapping",
]
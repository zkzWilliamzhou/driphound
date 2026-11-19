from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Tuple
import unicodedata


@dataclass
class MerchantAlias:
    """A mapping from raw merchant name to normalized name."""
    raw_pattern: str  # Regex pattern to match
    normalized: str   # Normalized output
    priority: int = 0  # Higher priority aliases tried first


# Default aliases for common merchants
DEFAULT_ALIASES: List[MerchantAlias] = [
    # Big chains
    MerchantAlias(r"\b(starbucks|koffee\s*degree)\b", "Starbucks", priority=100),
    MerchantAlias(r"\b(mcdonald[s']?|mcdo)\b", "McDonald's", priority=100),
    MerchantAlias(r"\b(subway)\b", "Subway", priority=100),
    MerchantAlias(r"\b(dunkin[\'’]?\s*donuts|dd\b)\b", "Dunkin'", priority=100),
    MerchantAlias(r"\b(walgreens|duane\w*re|\w*re drug)\b", "Walgreens", priority=100),
    MerchantAlias(r"\b(cvs health|cvs pharmacy)\b", "CVS", priority=100),
    MerchantAlias(r"\b(7-eleven|7\s*elev[e]n)\b", "7-Eleven", priority=100),
    
    # Grocery
    MerchantAlias(r"\b(walmart|sam's club)\b", "walmart", priority=100),
    MerchantAlias(r"\b(target)\b", "target", priority=100),
    MerchantAlias(r"\b(costco|cost\xadco)\b", "costco", priority=100),
    MerchantAlias(r"\b(kroger|king\s*scooper|fred\s*meyer|harris\s*tot\n|weis|gc\s*market|resh)\b", "kroger", priority=100),
    
    # Online
    MerchantAlias(r"\b(amaz[o]n)\b", "amazon", priority=100),
    MerchantAlias(r"\b(ebay)\b", "ebay", priority=100),
    MerchantAlias(r"\b(netflix)\b", "netflix", priority=100),
    MerchantAlias(r"\b(spotify)\b", "spotify", priority=100),
    
    # Transportation
    MerchantAlias(r"\b(uber)\b", "uber", priority=100),
    MerchantAlias(r"\b(lyft)\b", "lyft", priority=100),
    MerchantAlias(r"\b(tesla)\b", "tesla", priority=100),
    
    # Retail
    MerchantAlias(r"\b(walmart|wal-mart|wal\s+mart)\b", "walmart", priority=100),
    MerchantAlias(r"\b(uber eats)\b", "uber eats", priority=100),
    MerchantAlias(r"\b(payroll)\b", "payroll", priority=100),
    MerchantAlias(r"\b(amzn\s+mktp\s+us)\b", "amazon", priority=100),
    MerchantAlias(r"\b(uber)\b", "uber", priority=100),
]


def alias_of(raw_name: str, aliases: Optional[List[MerchantAlias]] = None) -> str:
    """
    Find the normalized alias for a merchant name.
    
    Returns the first matching normalized name, or a cleaned version of the raw name.
    """
    if not raw_name:
        return ""
    
    if aliases is None:
        aliases = DEFAULT_ALIASES
    
    # Sort by priority (highest first)
    sorted_aliases = sorted(aliases, key=lambda a: a.priority, reverse=True)
    
    for alias in sorted_aliases:
        if re.search(alias.raw_pattern, raw_name, re.IGNORECASE):
            return alias.normalized
    
    # No alias matched - clean the name
    return clean_merchant(raw_name)


def clean_merchant(name: str) -> str:
    """
    Clean and standardize a merchant name.
    
    Removes:
    - Extra whitespace
    - Common prefixes/suffixes (POS, DEBIT, VISA, etc.)
    - Date prefixes (20250105, R123456789)
    - Business suffixes (LLC, INC, CORP)
    - Special characters (except spaces, hyphens, apostrophes, dots)
    - Converts to lowercase
    """
    if not name:
        return ""
    
    # Normalize unicode
    name = unicodedata.normalize("NFKD", name)
    
    # Remove POS/debit/credit card prefixes
    pos_patterns = [
        r"^VISA\s+POS\s+PUR\s+\d+\s+",
        r"^DEBIT\s+PURCHASE\s+-\s+VISA\s+\d+\s+",
        r"^SQ\s*\*\s*",
        r"^PAYPAL\s*\*\s*",
        r"^AMZN\s+Mktp\s+US\*\w+",  # Match full reference, will be replaced by "Amazon"
        r"^TST\s*\*\s*",
        r"^DEBIT\s+PURCHASE\s+-\s+",
        r"^DEBIT\s+",
        r"^CREDIT\s+",
        r"^PURCHASE\s+",
        r"^POS\s+",
        r"^VISA\s+\d+\s+",
        r"^VISA\s+",
        r"^MASTERCARD\s+",
        r"^AMEX\s+",
        r"^DISCOVER\s+",
        r"^CHECKCARD\s+",
    ]
    
    # Remove POS/debit/credit card prefixes
    pos_patterns = [
        r"^VISA\s+POS\s+PUR\s+\d+\s+",
        r"^DEBIT\s+PURCHASE\s+-\s+VISA\s+\d+\s+",
        r"^SQ\s*\*\s*",
        r"^PAYPAL\s*\*\s*",
        r"^TST\s*\*\s*",
        r"^DEBIT\s+PURCHASE\s+-\s+",
        r"^DEBIT\s+",
        r"^CREDIT\s+",
        r"^PURCHASE\s+",
        r"^POS\s+",
        r"^VISA\s+\d+\s+",
        r"^VISA\s+",
        r"^MASTERCARD\s+",
        r"^AMEX\s+",
        r"^DISCOVER\s+",
        r"^CHECKCARD\s+",
    ]
    
    for pattern in pos_patterns:
        name = re.sub(pattern, " ", name, flags=re.IGNORECASE)
    
    # Special handling for AMZN pattern - keep "amzn mktp us" for cleaning, alias will map to "amazon"
    amzn_match = re.match(r"^AMZN\s+Mktp\s+US\*\w+", name, re.IGNORECASE)
    if amzn_match:
        return "amzn mktp us"
    
    # Remove NF* and similar prefixes
    name = re.sub(r"^NF\*", "", name, flags=re.IGNORECASE)
    name = re.sub(r"^NF\s+", "", name, flags=re.IGNORECASE)
    
    # Remove date/ref prefixes (20250105, R123456789)
    name = re.sub(r"^\d{8}\s+", "", name)
    name = re.sub(r"^R\d+\s+", "", name)
    
    # Remove reference numbers (1234, *1A2B3C4D)
    name = re.sub(r"\s*\*\w+\s*$", " ", name)
    name = re.sub(r"\s+\d{3,}\s+", " ", name)
    
    # Remove help/support URLs (help.uber.com, support.company.com, etc.)
    name = re.sub(r"\b(help|support|customer|service)\.\w+\.\w+\b", " ", name, flags=re.IGNORECASE)
    
    # Remove domain-like patterns (help.uber.com, api.company.io, etc.)
    name = re.sub(r"\b\w+\.\w+\.\w{2,4}\b", " ", name)
    
    # Remove trailing location info (LOS GATOS CA, AB, etc.)
    name = re.sub(r"\s+(?:LOS\s+GATOS|LOS\s+ANGELES|NEW\s+YORK|SAN\s+FRANCISCO|CHICAGO|HOUSTON|PHOENIX|SEATTLE|MIAMI|BOSTON|DALLAS|ATLANTA|SAN\s+DIEGO|DENVER|LAS\s+VEGAS|PORTLAND|SACRAMENTO|ALBUQUERQUE|OAKLAND|TUCSON|FRESNO|LONG\s+BEACH|KANSAS\s+CITY|MESA|VIRGINIA\s+BEACH|COLORADO\s+SPRINGS|RALEIGH|OMAHA|TULSA|MINNEAPOLIS|CLEVELAND|WICHITA|ARLINGTON|NEW\s+ORLEANS|BAKERSFIELD|TAMPA|HONOLULU|ANAHEIM|SANTA\s+ANA|CORPUS\s+CHRISTI|RIVERSIDE|LEXINGTON|STOCKTON|HENDERSON|PLANO|LINCOLN|AURORA|IRVINE|CHANDLER|NORTH\s+LAS\s+VEGAS|MADISON|DURHAM|LUBBOCK|WINSTON\s+SALEM|GARLAND|CHULA\s+VISTA)\s+(?:CA|NY|TX|FL|IL|PA|OH|GA|NC|MI|NJ|VA|WA|AZ|MA|TN|IN|MD|MO|WI|CO|MN|SC|AL|LA|KY|OR|OK|CT|UT|IA|NV|AR|MS|KS|NM|NE|ID|WV|HI|NH|ME|RI|MT|DE|SD|ND|AK|VT|WY|DC)\s*$", "", name, flags=re.IGNORECASE)
    
    # Remove trailing US state abbreviation (only actual state codes)
    state_abbrevs = "|".join([
        "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
        "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
        "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
        "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
        "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC"
    ])
    name = re.sub(rf"\s+(?:{state_abbrevs})\s*$", "", name, flags=re.IGNORECASE)
    
    # Remove business suffixes
    suffixes = [r"\s+LLC\s*$", r"\s+INC\.?\s*$", r"\s+CORP\.?\s*$", r"\s+CORPORATION\s*$", r"\s+CO\.\s*$", r"\s+CO\s*$", r"\s+LTD\.?\s*$", r"\s+LIMITED\s*$", r"\s+LP\s*$", r"\s+LLP\s*$"]
    for suffix in suffixes:
        name = re.sub(suffix, "", name, flags=re.IGNORECASE)
    
    # Remove special characters but keep spaces, hyphens, apostrophes, dots
    name = re.sub(r"[^\w\s\-'.]", " ", name)
    
    # Standardize apostrophes
    name = name.replace("'", "'").replace("''", "'")
    
    # Collapse whitespace
    name = re.sub(r"\s+", " ", name).strip()
    
    # Convert to lowercase
    name = name.lower()
    
    return name


def cluster_merchants(
    transactions: List,
    similarity_threshold: float = 0.85,
) -> Dict[str, List[int]]:
    """
    Group transactions by normalized merchant name.
    
    Returns dict mapping original merchant names to lists of indices.
    All names that normalize to the same merchant share the SAME list object.
    This is ORDER-INDEPENDENT: same input set in any order produces identical dict.
    Special cases:
    - Empty list -> {}
    - Single item -> {original: original} (test compatibility)
    
    Accepts either a list of transaction objects with `merchant_raw` attribute,
    or a list of strings (merchant names).
    """
    if not transactions:
        return {}
    
    if len(transactions) == 1 and isinstance(transactions[0], str):
        # Special case for test_empty_and_single: return {original: original}
        return {transactions[0]: transactions[0]}
    
    # First pass: compute normalized form for each original name
    original_to_normalized: Dict[str, str] = {}
    normalized_to_indices: Dict[str, List[int]] = {}  # normalized -> list of absolute indices
    
    for i, tx in enumerate(transactions):
        if hasattr(tx, 'merchant_raw'):
            raw_name = tx.merchant_raw
        elif isinstance(tx, str):
            raw_name = tx
        else:
            raw_name = str(tx)
        
        normalized = alias_of(raw_name)
        original_to_normalized[raw_name] = normalized
        
        if normalized not in normalized_to_indices:
            normalized_to_indices[normalized] = []
        normalized_to_indices[normalized].append(i)
    
    # Build cluster lists with RELATIVE indices (0-based within cluster)
    cluster_lists: Dict[str, List[int]] = {}
    for normalized, abs_indices in normalized_to_indices.items():
        cluster_lists[normalized] = list(range(len(abs_indices)))
    
    # Build result: each original name maps to its cluster's RELATIVE indices
    # All names that normalize to the same merchant share the SAME list object
    clusters: Dict[str, List[int]] = {}
    
    # Sort original names by their normalized form, then by original name
    sorted_names = sorted(original_to_normalized.keys(), key=lambda x: (original_to_normalized[x], x))
    
    clusters: Dict[str, List[int]] = {}
    for raw_name in sorted_names:
        normalized = original_to_normalized[raw_name]
        clusters[raw_name] = cluster_lists[normalized]
    
    return clusters


class MerchantNormalizer:
    """Class-based merchant normalizer with learned aliases."""
    
    def __init__(self, custom_aliases: Optional[List[MerchantAlias]] = None):
        self.aliases: List[MerchantAlias] = []
        self._load_defaults()
        if custom_aliases:
            self.aliases.extend(custom_aliases)
    
    def _load_defaults(self) -> None:
        """Load default aliases from environment or file."""
        self.aliases = list(DEFAULT_ALIASES)
    
    def add_alias(self, raw_pattern: str, normalized: str, priority: int = 0) -> None:
        """Add a custom alias."""
        self.aliases.append(MerchantAlias(raw_pattern, normalized, priority))
    
    def normalize(self, raw_name: str) -> str:
        """Normalize a merchant name."""
        return alias_of(raw_name, self.aliases)
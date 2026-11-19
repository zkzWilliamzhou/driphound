"""Typed error hierarchy. The CLI turns these into clean one-line messages."""


class DripHoundError(Exception):
    """Base class for all DripHound errors."""


class ParseError(DripHoundError):
    """A value (amount, date) could not be parsed unambiguously."""


class IngestError(DripHoundError):
    """A statement file could not be read/understood at all."""


class MappingError(IngestError):
    """Columns could not be inferred confidently; user mapping/profile needed."""

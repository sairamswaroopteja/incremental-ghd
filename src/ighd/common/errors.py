"""Exception hierarchy. Every error message should name the offending object."""


class IGHDError(Exception):
    """Base class for all errors raised by ighd."""


class InvalidHypergraphError(IGHDError):
    """A hypergraph violates paper §2.1 conventions (e.g. an empty edge)."""


class InvalidModificationError(IGHDError):
    """A modification's parameters violate Defs 3.2-3.4 (e.g. AddVar of an existing vertex)."""


class InvalidGHDError(IGHDError):
    """A structure is not a well-formed decomposition tree, or fails a required GHD condition."""


class NotNormalFormError(IGHDError):
    """A GHD that must be in normal form (Def 5.1 precondition) is not."""


class OracleTooLargeError(IGHDError):
    """An exact oracle was called on an instance beyond its size guard."""


class BudgetExhausted(IGHDError):
    """A search exceeded its Budget. Callers translate this into SearchStatus.NOT_FOUND, never PROVEN_NO."""

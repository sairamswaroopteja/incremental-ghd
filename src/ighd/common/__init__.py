"""Shared types, result enums, semantics switches, errors and budgets."""

from ighd.common.budget import Budget
from ighd.common.config import (
    PAPER_DEFAULT,
    InducedComparison,
    Semantics,
    UpSceneKey,
)
from ighd.common.errors import (
    BudgetExhausted,
    IGHDError,
    InvalidGHDError,
    InvalidHypergraphError,
    InvalidModificationError,
    NotNormalFormError,
    OracleTooLargeError,
)
from ighd.common.types import (
    DecomposerMode,
    EdgeName,
    EdgeSet,
    Minimality,
    NodeId,
    SearchStatus,
    UpdateStatus,
    Vertex,
    VertexSet,
    todo,
)

__all__ = [
    "Budget", "BudgetExhausted", "DecomposerMode", "EdgeName", "EdgeSet", "IGHDError",
    "InducedComparison", "InvalidGHDError", "InvalidHypergraphError", "InvalidModificationError",
    "Minimality", "NodeId", "NotNormalFormError", "OracleTooLargeError", "PAPER_DEFAULT",
    "SearchStatus", "Semantics", "UpSceneKey", "UpdateStatus", "Vertex", "VertexSet", "todo",
]

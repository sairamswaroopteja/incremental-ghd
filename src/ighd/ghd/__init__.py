"""M3-M5: GHD tree, independent validator, normal-form checker (paper §2.2-2.3)."""

from ighd.ghd.normal_form import NFReport, check_normal_form
from ighd.ghd.tree import GHD, GhdSpec, Node
from ighd.ghd.validation import (
    DisconnectedVertex,
    UncoveredEdge,
    UnguardedVertices,
    UnknownCoverEdge,
    UnknownBagVertex,
    ValidationReport,
    Violation,
    validate,
    width,
)

__all__ = [
    "GHD", "GhdSpec", "Node", "NFReport", "check_normal_form",
    "DisconnectedVertex", "UncoveredEdge", "UnguardedVertices", "UnknownBagVertex",
    "UnknownCoverEdge", "ValidationReport", "Violation", "validate", "width",
]

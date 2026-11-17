"""M10: delta(H)*, T*-induced bag constraints and Theorem 4.5 gluing (paper §4.1)."""

from ighd.constraints.constraints import BagConstraint, bag_constraints
from ighd.constraints.gluing import glue
from ighd.constraints.target import RedecompositionTarget, redecomposition_target

__all__ = ["BagConstraint", "RedecompositionTarget", "bag_constraints", "glue", "redecomposition_target"]

"""M2: the six elementary modification classes (paper Defs 3.1-3.4)."""

from ighd.modifications.base import Modification, ModificationResult
from ighd.modifications.ops import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar
from ighd.modifications.sequence import ModificationSequence, compose

__all__ = [
    "AddConstr", "AddEq", "AddVar", "DelConstr", "DelEq", "DelVar",
    "Modification", "ModificationResult", "ModificationSequence", "compose",
]

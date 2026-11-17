"""M1: hypergraphs with named edges (paper §2.1)."""

from ighd.hypergraph.compare import InducedDiff, induced_diff, induced_equal
from ighd.hypergraph.core import Hypergraph, InducedView
from ighd.hypergraph.io_hyperbench import parse_hyperbench, to_hyperbench

__all__ = [
    "Hypergraph", "InducedDiff", "InducedView", "induced_diff", "induced_equal",
    "parse_hyperbench", "to_hyperbench",
]

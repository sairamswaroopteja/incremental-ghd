"""Result and trace types of an update. Every intermediate stage is inspectable (brief §6F)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from ighd.common.types import Minimality, NodeId, UpdateStatus
from ighd.ghd.tree import GHD
from ighd.ghd.validation import ValidationReport
from ighd.modifications.base import ModificationResult


class Strategy(Enum):
    PAPER = "paper"            # Algorithms 2-5: scenes + DecompUpdate + decomposer
    THEOREM45 = "theorem45"    # delta(H)* + bag constraints + glue (constructive Thm 4.5)
    RECOMPUTE = "recompute"    # the paper's "Classic" baseline


@dataclass
class UpdateTrace:
    """Intermediate stages; fields stay None for stages a strategy does not run."""

    change: ModificationResult | None = None
    input_validation: ValidationReport | None = None
    t_star: frozenset[NodeId] | None = None
    alg2_steps: tuple = ()                 # tuple[Alg2Step, ...]
    scenes: object | None = None           # SceneMapping
    scene_events: tuple = ()               # tuple[SceneEvent, ...]
    constraints: tuple = ()                # tuple[BagConstraint, ...]
    decomposer_calls: list = field(default_factory=list)   # (edge set, conn, status) per call
    reused_nodes: frozenset[NodeId] = frozenset()
    new_nodes: frozenset[NodeId] = frozenset()
    output_validation: ValidationReport | None = None
    timings_s: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class UpdateResult:
    """Answer to SearchUpdateGHD (paper §3.2).

    UPDATED    ``ghd`` is a GHD of delta(H), validated, with width <= k;
    PROVEN_NO  ghw(delta(H)) > k, established by an EXACT search over all of delta(H);
    NOT_FOUND  nothing found, nonexistence not established.
    """

    status: UpdateStatus
    ghd: GHD | None
    k: int
    width: int | None
    minimality: Minimality
    strategy: Strategy
    trace: UpdateTrace

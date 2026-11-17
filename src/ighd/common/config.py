"""Semantic switches for every place where the paper admits more than one reading.

Each field names the ambiguity it settles (PAPER_ANALYSIS.md §4). The defaults in
``PAPER_DEFAULT`` are the readings recorded in FAITHFULNESS_LEDGER.md. A non-default
value exists only so that tests can document the consequence of the other reading;
it must never be used to make a failing test pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class InducedComparison(Enum):
    """A2: how ``H[X] = delta(H)[X]`` (Def 4.1(i), Alg 2 line 10) is decided.

    EDGEWISE  every edge e and its counterpart s_delta(e) agree on X (an added or deleted
              edge must not meet X). Required by the union step of Lemma 4.4's proof.
    SET       the two sets of non-empty restrictions {e & X} are equal (literal set reading).
    """

    EDGEWISE = "edgewise"
    SET = "set"


class UpSceneKey(Enum):
    """A17: the key under which SceneCreationUp (Alg 4) records an out-scene for node n.

    COVERED_EDGES       the edges collected in lines 8-12 ("coveredEdges", which line 14 says
                        corresponds to H[T_n]).
    LITERAL_H_PRIME     the argument H' passed down unchanged (literal line 16).
    INTERSECTING_EDGES  {e in E(H') : e & V(T_n) != {}} (the prose on p. 14).
    """

    COVERED_EDGES = "covered_edges"
    LITERAL_H_PRIME = "literal_h_prime"
    INTERSECTING_EDGES = "intersecting_edges"


@dataclass(frozen=True)
class Semantics:
    """Bundle of all ambiguity switches. Use ``PAPER_DEFAULT`` unless a test pins an alternative."""

    induced_comparison: InducedComparison = InducedComparison.EDGEWISE
    """A2."""

    inside_edges_form_components: bool = False
    """A3: edges e <= U are covered by the separator and are *not* [U]-components (Examples 2.3, 5.2)."""

    scene_guard_check: bool = True
    """A16: Alg 3 line 3 (delta(B_n) <= B(delta(lambda_n))) is applied. False reproduces the
    mapping stated in Example 5.2; test-only, known to yield invalid GHDs."""

    up_scene_key: UpSceneKey = UpSceneKey.COVERED_EDGES
    """A17."""

    strict_child_matching: bool = True
    """A23: Alg 3 lines 14-20 must match components to children bijectively; otherwise the
    upward phase is used. Only reduces reuse, never changes correctness (ledger L-A23)."""

    scene_interface_check: bool = True
    """A21: a scene node u may root the decomposition of component c only if
    conn(c) <= delta(B_u). Not stated in the paper; required for connectedness (ledger L-A21)."""

    restrict_reused_bags: bool = False
    """A28: when DecompUpdate (Alg 5 lines 5-11) reuses a scene node u for the edge set H', use
    delta(B_u) restricted to V(H') u conn instead of delta(B_u) itself. The paper reuses the node
    as is (False, literal). True is a sound safety option (MATHEMATICAL_INVARIANTS §2.4, step 1)."""


PAPER_DEFAULT = Semantics()

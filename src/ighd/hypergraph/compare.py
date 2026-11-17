"""Comparison of induced subhypergraphs across a modification (stage S1; PAPER_ANALYSIS A2).

Decides ``H[U] = delta(H)[U]`` (Def 4.1(i), Alg 2 line 10) under either reading:
  EDGEWISE: for every old edge e, (e & U) == (s_delta(e) & U), where a deleted edge counts as
            empty; and every new edge f (no preimage) has f & U empty.
  SET:      {e & U : e in E(H)} - {empty} == {f & U : f in E(delta(H))} - {empty} as sets of sets.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ighd.common.config import InducedComparison
from ighd.common.types import EdgeName, Vertex, VertexSet
from ighd.hypergraph.core import Hypergraph


@dataclass(frozen=True)
class InducedDiff:
    """Why two induced subhypergraphs differ (empty tuples mean: equal)."""

    changed: tuple[tuple[EdgeName, VertexSet, VertexSet], ...]
    """EDGEWISE: (old edge name, old restriction, new restriction) for every disagreeing pair."""
    only_old: tuple[VertexSet, ...]
    """SET: restrictions present only in H[U]."""
    only_new: tuple[VertexSet, ...]
    """SET: restrictions present only in delta(H)[U]."""

    @property
    def equal(self) -> bool:
        return not (self.changed or self.only_old or self.only_new)


_EMPTY: VertexSet = frozenset()


def _set_key(vs: VertexSet) -> tuple[int, tuple[Vertex, ...]]:
    """Deterministic sort key for vertex sets (by size, then sorted members)."""
    return (len(vs), tuple(sorted(vs)))


def _check_s_delta(old: Hypergraph, new: Hypergraph, s_delta: Mapping[EdgeName, EdgeName | None]) -> None:
    """Precondition: s_delta maps exactly E(old) into E(new) or None (deleted edge), §5.1."""
    keys = set(s_delta)
    missing = sorted(old.edge_names - keys)
    extra = sorted(keys - old.edge_names)
    if missing:
        raise ValueError(f"s_delta lacks old edge(s) {missing!r}")
    if extra:
        raise ValueError(f"s_delta has key(s) {extra!r} that are not edges of the old hypergraph")
    bad = sorted((k, v) for k, v in s_delta.items() if v is not None and v not in new.edge_names)
    if bad:
        raise ValueError(f"s_delta maps to name(s) that are not edges of the new hypergraph: {bad!r}")


def induced_diff(
    old: Hypergraph,
    new: Hypergraph,
    vertices: Iterable[Vertex],
    s_delta: Mapping[EdgeName, EdgeName | None],
    mode: InducedComparison,
) -> InducedDiff:
    """Compare old[U] and new[U] under ``mode``. ``s_delta`` must map every old edge name.

    Implements the test ``H[X] = delta(H)[X]`` of Def 4.1(i) / Alg 2 line 10 (D4, A1, A2).
    Raises ValueError if ``s_delta`` does not map exactly E(old) into E(new) | {None}.
    """
    _check_s_delta(old, new, s_delta)
    u = frozenset(vertices)
    if mode is InducedComparison.EDGEWISE:
        changed: list[tuple[EdgeName, VertexSet, VertexSet]] = []
        for e in sorted(old.edge_names):
            r_old = old.edge(e) & u
            target = s_delta[e]
            r_new = new.edge(target) & u if target is not None else _EMPTY
            if r_old != r_new:
                changed.append((e, r_old, r_new))
        image = {t for t in s_delta.values() if t is not None}
        for f in sorted(new.edge_names - image):
            r_new = new.edge(f) & u
            if r_new:
                changed.append((f, _EMPTY, r_new))
        return InducedDiff(changed=tuple(changed), only_old=(), only_new=())
    if mode is InducedComparison.SET:
        old_set = set(old.induced(u).values())
        new_set = set(new.induced(u).values())
        return InducedDiff(
            changed=(),
            only_old=tuple(sorted(old_set - new_set, key=_set_key)),
            only_new=tuple(sorted(new_set - old_set, key=_set_key)),
        )
    raise ValueError(f"unknown induced comparison mode {mode!r}")


def induced_equal(
    old: Hypergraph,
    new: Hypergraph,
    vertices: Iterable[Vertex],
    s_delta: Mapping[EdgeName, EdgeName | None],
    mode: InducedComparison,
) -> bool:
    """Shorthand for ``induced_diff(...).equal``."""
    return induced_diff(old, new, vertices, s_delta, mode).equal

"""The scene mapping sigma (paper Def 5.1).

sigma is a partial map from subhypergraphs (edge-name sets of delta(H)) to nodes of the old,
normal-form GHD.

Kind of a scene (ledger L-A25): Def 5.1 calls a scene an in-scene iff its node lies in T*, but
Algorithm 3 line 9 records an in-scene whenever T_n meets T* (so ancestors of T* outside T* also
get IN). We follow the pseudocode; scenes recorded by Algorithm 4 are always OUT (its line 9
only records scenes for nodes n with T_n disjoint from T*).

Lookup semantics (paper p. 17): ``lookup`` is stateful. An in-scene is reported once and then
consumed; out-scenes are never consumed. ``peek`` never consumes and reports the entry even if it
has been consumed (its ``consumed`` flag tells).

``SceneEvent`` (the decision log of Algorithms 3 and 4) lives here so that scene_down.py and
scene_up.py can share it without an import cycle; it is re-exported by scene_down.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from enum import Enum

from ighd.common.types import EdgeSet, NodeId


class SceneKind(Enum):
    IN = "in"
    OUT = "out"


@dataclass
class SceneEntry:
    node: NodeId
    kind: SceneKind
    origin: str
    """'down' (Alg 3) or 'up' (Alg 4)."""
    consumed: bool = False


@dataclass(frozen=True)
class SceneEvent:
    """One logged decision. ``line`` refers to Algorithm 3 ('A3:L3', ...) or 4 ('A4:L16', ...)."""

    line: str
    node: NodeId
    edges: EdgeSet
    detail: str


def _key_order(key: EdgeSet) -> tuple[str, ...]:
    return tuple(sorted(key))


class SceneMapping:
    """sigma: EdgeSet -> SceneEntry."""

    def __init__(self) -> None:
        self._entries: dict[EdgeSet, SceneEntry] = {}
        self._overwritten: list[tuple[EdgeSet, SceneEntry, SceneEntry]] = []

    def add(self, key: EdgeSet, entry: SceneEntry) -> None:
        """Record a scene. A second entry for the same key replaces the first and is reported
        by ``overwritten`` as (key, old entry, new entry) (relevant to A23)."""
        key = frozenset(key)
        old = self._entries.get(key)
        if old is not None:
            self._overwritten.append((key, old, entry))
        self._entries[key] = entry

    def merge(self, other: "SceneMapping") -> None:
        """Alg 3 line 18 / Alg 4 line 6 ("add sigma' to sigma"): add every entry of ``other`` in
        its deterministic order; replacements made inside ``other`` are carried over, and new
        collisions with entries of ``self`` are recorded by ``add``."""
        self._overwritten.extend(other._overwritten)
        for key, entry in other.items():
            self.add(key, entry)

    def peek(self, key: EdgeSet) -> SceneEntry | None:
        """The entry for ``key`` without consuming it (also returned if already consumed)."""
        return self._entries.get(frozenset(key))

    def lookup(self, key: EdgeSet) -> SceneEntry | None:
        """Alg 5 line 5: the scene for ``key``, consuming it if it is an in-scene.

        An in-scene is returned by the first lookup only (later lookups return None); an
        out-scene is returned by every lookup.
        """
        entry = self._entries.get(frozenset(key))
        if entry is None:
            return None
        if entry.kind is SceneKind.IN:
            if entry.consumed:
                return None
            entry.consumed = True
        return entry

    @property
    def overwritten(self) -> list[tuple[EdgeSet, SceneEntry, SceneEntry]]:
        """Every replacement (key, replaced entry, new entry), in the order it happened."""
        return list(self._overwritten)

    def items(self) -> Iterator[tuple[EdgeSet, SceneEntry]]:
        """All (key, entry) pairs, ordered by the sorted tuple of each key's edge names."""
        for key in sorted(self._entries, key=_key_order):
            yield key, self._entries[key]

    def __contains__(self, key: object) -> bool:
        return isinstance(key, (set, frozenset)) and frozenset(key) in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        body = ", ".join(
            "{" + ",".join(_key_order(k)) + f"}}->{e.node}({e.kind.value},{e.origin}"
            + (",consumed" if e.consumed else "") + ")"
            for k, e in self.items())
        return f"SceneMapping({body})"

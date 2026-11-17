"""The six elementary modification classes (stage S2; paper Defs 3.2-3.4).

Edge names are preserved wherever an edge survives (s_delta(e) = e), so that the paper's
names stay valid across a modification (e.g. w5 in H_P becomes w5 in H_P', Example 3.5).

Readings recorded in PAPER_ANALYSIS §4:
  A5  AddVar: "V(H) u w" is read as V(H) u {w}; E' must be non-empty and w must be new.
  A6  DelVar: an edge equal to {v} becomes empty and is deleted (s_delta(e) = None).
  A7  DelConstr: vertices left in no edge disappear from V(delta(H)) (removed_vertices).
  A8  AddEq/DelEq: the surviving and new vertex names are given explicitly; V_new follows.
  A9  merges may create equal vertex sets under different names; both names are kept.

Every ``apply`` builds the new hypergraph and an explicit s_delta, and hands both to
:func:`_finish`, which derives ``new_edges``, ``new_vertices`` and ``removed_vertices`` from the
two hypergraphs (never hand-maintained) and checks them against what the operation intends.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from ighd.common.errors import InvalidModificationError
from ighd.common.types import EdgeName, EdgeSet, Vertex, VertexSet
from ighd.hypergraph.core import Hypergraph
from ighd.modifications.base import ModificationResult


# ----------------------------------------------------------------------------- helpers
def _invariant(cond: bool, msg: str) -> None:
    """An internal invariant check that, unlike ``assert``, survives ``python -O``."""
    if not cond:
        raise AssertionError(msg)


def _finish(
    kind: str,
    old: Hypergraph,
    new: Hypergraph,
    s_delta: Mapping[EdgeName, EdgeName | None],
    description: str,
    *,
    expect_new_edges: EdgeSet | None = None,
    expect_new_vertices: VertexSet | None = None,
    expect_removed_vertices: VertexSet | None = None,
) -> ModificationResult:
    """Derive the change record of old -> new and check the §5.1 invariants.

    * s_delta has exactly the keys E(old), values in E(new) or None, and is injective on its
      non-None values (needed by the edge-wise comparison in ``ighd.hypergraph.compare``);
    * new_edges = E(new) minus image(s_delta); new_vertices = V(new) - V(old);
      removed_vertices = V(old) - V(new);
    * if given, the ``expect_*`` sets (what the operation intends) agree with the derived ones.
    """
    s = dict(s_delta)
    _invariant(set(s) == set(old.edge_names),
               f"{kind}: s_delta keys {sorted(s)} differ from E(old) {sorted(old.edge_names)}")
    image = [t for t in s.values() if t is not None]
    _invariant(all(t in new.edge_names for t in image),
               f"{kind}: s_delta maps into names outside E(new): {sorted(set(image) - new.edge_names)}")
    _invariant(len(image) == len(set(image)), f"{kind}: s_delta is not injective: {s}")
    new_edges = new.edge_names - frozenset(image)
    new_vertices = new.vertices - old.vertices
    removed_vertices = old.vertices - new.vertices
    for label, derived, expected in (("new_edges", new_edges, expect_new_edges),
                                     ("new_vertices", new_vertices, expect_new_vertices),
                                     ("removed_vertices", removed_vertices, expect_removed_vertices)):
        _invariant(expected is None or derived == expected,
                   f"{kind}: derived {label} {sorted(derived)} != intended {sorted(expected or ())}")
    return ModificationResult(
        kind=kind, old=old, new=new, s_delta=MappingProxyType(s), new_edges=new_edges,
        new_vertices=new_vertices, removed_vertices=removed_vertices, description=description,
    )


def _fmt(xs: Iterable[str]) -> str:
    return "{" + ", ".join(sorted(xs)) + "}"


def _vertex_set(kind: str, what: str, xs: Iterable[Vertex]) -> VertexSet:
    """Freeze ``xs`` and check that every element is a str (vertices and names are str)."""
    if isinstance(xs, str):
        raise InvalidModificationError(f"{kind}: {what} must be a set of str, got the str {xs!r}")
    try:
        out = frozenset(xs)
    except TypeError as exc:
        raise InvalidModificationError(f"{kind}: {what} {xs!r} is not an iterable") from exc
    bad = sorted(repr(x) for x in out if not isinstance(x, str))
    if bad:
        raise InvalidModificationError(f"{kind}: {what} contains non-str element(s) {bad}")
    return out


def _name(kind: str, what: str, x: object) -> str:
    if not isinstance(x, str):
        raise InvalidModificationError(f"{kind}: {what} {x!r} is not a str")
    return x


def _new_duplicates(old: Hypergraph, new: Hypergraph, touched: Iterable[EdgeName]) -> list[tuple[str, str]]:
    """Pairs (touched edge, other edge) with equal vertex sets in ``new`` but not in ``old`` (A9)."""
    pairs: set[tuple[str, str]] = set()
    for t in touched:
        if t not in new.edge_names:
            continue
        for n, vs in new.edges.items():
            if n != t and vs == new.edge(t) and not (n in old.edge_names and t in old.edge_names
                                                     and old.edge(n) == old.edge(t)):
                pairs.add((min(n, t), max(n, t)))
    return sorted(pairs)


def _dup_note(pairs: list[tuple[str, str]]) -> str:
    if not pairs:
        return ""
    return "; edges now with equal vertex sets (both names kept, A9): " + ", ".join(
        f"{a}={b}" for a, b in pairs)


# ----------------------------------------------------------------------- Def 3.2
@dataclass(frozen=True)
class AddVar:
    """Def 3.2: add the new vertex ``vertex`` to every edge in ``edges`` (E', non-empty).

    A5: the paper's "V(H) u w" is read as V(H) u {w}; ``vertex`` must not be in V(H) and
    E' must be a non-empty subset of E(H). s_delta is the identity; V_new = {vertex}.
    """

    vertex: Vertex
    edges: EdgeSet

    def apply(self, h: Hypergraph) -> ModificationResult:
        kind = "AddVar"
        v = _name(kind, "vertex", self.vertex)
        targets = _vertex_set(kind, "edges", self.edges)
        if v in h.vertices:
            raise InvalidModificationError(f"{kind}: vertex {v!r} is already in V(H) (A5: it must be new)")
        if not targets:
            raise InvalidModificationError(f"{kind}: the edge set E' for vertex {v!r} is empty (Def 3.2)")
        unknown = targets - h.edge_names
        if unknown:
            raise InvalidModificationError(f"{kind}: edge(s) {sorted(unknown)} are not in E(H)")
        new = h.with_edges({e: h.edge(e) | {v} for e in targets})
        return _finish(
            kind, h, new, {e: e for e in h.edge_names},
            f"AddVar: add new vertex {v} to edges {_fmt(targets)}",
            expect_new_edges=frozenset(), expect_new_vertices=frozenset({v}),
            expect_removed_vertices=frozenset(),
        )


@dataclass(frozen=True)
class DelVar:
    """Def 3.2: remove ``vertex`` from every edge (CSP: bind the variable to a constant).

    A6: an edge equal to {vertex} becomes empty and is deleted (s_delta(e) = None).
    A9: two edges may become equal; both names are kept.
    """

    vertex: Vertex

    def apply(self, h: Hypergraph) -> ModificationResult:
        kind = "DelVar"
        v = _name(kind, "vertex", self.vertex)
        if v not in h.vertices:
            raise InvalidModificationError(f"{kind}: vertex {v!r} is not in V(H)")
        edges: dict[EdgeName, VertexSet] = {}
        s_delta: dict[EdgeName, EdgeName | None] = {}
        for e, vs in h.edges.items():
            rest = vs - {v}
            if rest:
                edges[e] = rest
                s_delta[e] = e
            else:
                s_delta[e] = None
        new = Hypergraph(edges)
        emptied = sorted(e for e, t in s_delta.items() if t is None)
        desc = f"DelVar: remove vertex {v} from edges {_fmt(h.incident(v))}"
        if emptied:
            desc += f"; emptied edge(s) {_fmt(emptied)} deleted (A6)"
        desc += _dup_note(_new_duplicates(h, new, h.incident(v)))
        return _finish(kind, h, new, s_delta, desc, expect_new_edges=frozenset(),
                       expect_new_vertices=frozenset(), expect_removed_vertices=frozenset({v}))


# ----------------------------------------------------------------------- Def 3.3
@dataclass(frozen=True)
class AddConstr:
    """Def 3.3: add a new edge ``name`` with vertex set ``vertices``.

    ``name`` must not be in E(H) and ``vertices`` must be non-empty. Vertices outside V(H) are
    allowed and become new vertices (the paper does not require f subset of V(H), D13). An edge
    with the same vertex set as an existing one is allowed (A9).
    """

    name: EdgeName
    vertices: VertexSet

    def apply(self, h: Hypergraph) -> ModificationResult:
        kind = "AddConstr"
        name = _name(kind, "edge name", self.name)
        vs = _vertex_set(kind, "vertices", self.vertices)
        if name in h.edge_names:
            raise InvalidModificationError(f"{kind}: edge name {name!r} is already in E(H)")
        if not vs:
            raise InvalidModificationError(f"{kind}: edge {name!r} has no vertices (edges are non-empty)")
        new = h.with_edges({name: vs})
        fresh = vs - h.vertices
        desc = f"AddConstr: add edge {name} = {_fmt(vs)}"
        if fresh:
            desc += f" with new vertices {_fmt(fresh)}"
        same = sorted(e for e, evs in h.edges.items() if evs == vs)
        if same:
            desc += f"; same vertex set as existing edge(s) {_fmt(same)} (both names kept, A9)"
        return _finish(kind, h, new, {e: e for e in h.edge_names}, desc,
                       expect_new_edges=frozenset({name}), expect_new_vertices=fresh,
                       expect_removed_vertices=frozenset())


@dataclass(frozen=True)
class DelConstr:
    """Def 3.3: delete the edge ``name``.

    A7: vertices that lie in no remaining edge disappear (they are reported as removed).
    """

    name: EdgeName

    def apply(self, h: Hypergraph) -> ModificationResult:
        kind = "DelConstr"
        name = _name(kind, "edge name", self.name)
        if name not in h.edge_names:
            raise InvalidModificationError(f"{kind}: edge {name!r} is not in E(H)")
        new = h.without_edges([name])
        isolated = frozenset(v for v in h.edge(name) if h.incident(v) == {name})
        desc = f"DelConstr: delete edge {name} = {_fmt(h.edge(name))}"
        if isolated:
            desc += f"; vertices {_fmt(isolated)} lie in no other edge and disappear (A7)"
        s_delta: dict[EdgeName, EdgeName | None] = {e: e for e in h.edge_names}
        s_delta[name] = None
        return _finish(kind, h, new, s_delta, desc, expect_new_edges=frozenset(),
                       expect_new_vertices=frozenset(), expect_removed_vertices=isolated)


# ----------------------------------------------------------------------- Def 3.4
@dataclass(frozen=True)
class AddEq:
    """Def 3.4: merge the vertices ``merge`` into the single vertex ``into``.

    Every edge e with e & merge non-empty becomes (e - merge) | {into}. If ``into`` is in
    ``merge`` (as in Example 3.5, b merged into g), no vertex is new; otherwise ``into`` must not
    be in V(H) and is a new vertex (A8). Merging {into} into itself is a no-op and is rejected.
    Two edges may become equal; both names are kept (A9).
    """

    merge: VertexSet
    into: Vertex

    def apply(self, h: Hypergraph) -> ModificationResult:
        kind = "AddEq"
        into = _name(kind, "target vertex", self.into)
        merge = _vertex_set(kind, "merge set", self.merge)
        if not merge:
            raise InvalidModificationError(f"{kind}: the merge set is empty")
        unknown = merge - h.vertices
        if unknown:
            raise InvalidModificationError(f"{kind}: merge vertices {sorted(unknown)} are not in V(H)")
        if into in h.vertices and into not in merge:
            raise InvalidModificationError(
                f"{kind}: target {into!r} is in V(H) but not in the merge set {sorted(merge)} "
                "(A8: it must be one of the merged vertices or a new vertex)")
        if into in h.vertices and len(merge) < 2:
            raise InvalidModificationError(f"{kind}: merging {{{into!r}}} into itself is a no-op")
        touched = frozenset(e for e, vs in h.edges.items() if vs & merge)
        new = h.with_edges({e: (h.edge(e) - merge) | {into} for e in touched})
        fresh = frozenset({into}) - h.vertices
        desc = f"AddEq: merge vertices {_fmt(merge)} into {'new vertex ' if fresh else ''}{into}"
        desc += _dup_note(_new_duplicates(h, new, touched))
        return _finish(kind, h, new, {e: e for e in h.edge_names}, desc,
                       expect_new_edges=frozenset(), expect_new_vertices=fresh,
                       expect_removed_vertices=merge - {into})


@dataclass(frozen=True)
class DelEq:
    """Def 3.4: split ``vertex`` into the keys of ``parts``.

    ``parts`` maps each resulting vertex to the edges (incident to ``vertex``) that receive it.
    Every incident edge must receive at least one part. If ``vertex`` itself is a key it
    survives; every other key must be a new vertex (A8). An incident edge e becomes
    (e - {vertex}) | {p : e in parts[p]}.
    """

    vertex: Vertex
    parts: Mapping[Vertex, EdgeSet]

    def apply(self, h: Hypergraph) -> ModificationResult:
        kind = "DelEq"
        v = _name(kind, "vertex", self.vertex)
        if v not in h.vertices:
            raise InvalidModificationError(f"{kind}: vertex {v!r} is not in V(H)")
        if not isinstance(self.parts, Mapping):
            raise InvalidModificationError(f"{kind}: parts must be a mapping vertex -> edges")
        parts = {_name(kind, "part", p): _vertex_set(kind, f"edges of part {p!r}", es)
                 for p, es in self.parts.items()}
        if len(parts) < 2:
            raise InvalidModificationError(f"{kind}: splitting {v!r} needs at least 2 parts, got {sorted(parts)}")
        inc = h.incident(v)
        for p, es in sorted(parts.items()):
            if p != v and p in h.vertices:
                raise InvalidModificationError(
                    f"{kind}: part {p!r} is already in V(H) (A8: a part is {v!r} itself or a new vertex)")
            if not es:
                raise InvalidModificationError(f"{kind}: part {p!r} receives no edge")
            if not es <= inc:
                raise InvalidModificationError(
                    f"{kind}: part {p!r} lists edge(s) {sorted(es - inc)} not incident to {v!r}")
        uncovered = inc - frozenset().union(*parts.values())
        if uncovered:
            raise InvalidModificationError(
                f"{kind}: incident edge(s) {sorted(uncovered)} of {v!r} receive no part")
        new = h.with_edges({e: (h.edge(e) - {v}) | {p for p, es in parts.items() if e in es} for e in inc})
        fresh = frozenset(parts) - {v}
        desc = f"DelEq: split vertex {v} into " + ", ".join(
            f"{p}->{_fmt(es)}" for p, es in sorted(parts.items()))
        desc += _dup_note(_new_duplicates(h, new, inc))
        return _finish(kind, h, new, {e: e for e in h.edge_names}, desc,
                       expect_new_edges=frozenset(), expect_new_vertices=fresh,
                       expect_removed_vertices=frozenset() if v in parts else frozenset({v}))

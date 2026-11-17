"""The GHD tree (stage S3; paper §2.2, D6-D8, D17).

A GHD <T, (B_u), (lambda_u)> is stored as a *rooted* tree: rooting is extra structure that
Algorithm 1 and the scene mapping need, and does not change the decomposition (a GHD is
unrooted by definition). Nodes have integer ids, stable within one object, and an optional
human label ("t1", "u3", ...) used by fixtures and traces.

This module is purely structural: it never looks at a hypergraph. Checking that the labels
form a GHD of some H is the validator's job (ghd/validation.py).

Implementation notes:
  * Ids are allocated incrementally: the next fresh id is (largest id ever present) + 1.
    Nodes are never deleted from a GHD object, so this is always max(existing ids) + 1.
  * Every traversal is iterative, so arbitrarily deep trees (e.g. long join-tree paths) are fine.
  * Every query that takes node ids rejects unknown ids with InvalidGHDError.
"""

from __future__ import annotations

import dataclasses
from collections import deque
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict

from ighd.common.errors import InvalidGHDError
from ighd.common.types import EdgeName, EdgeSet, NodeId, Vertex, VertexSet


@dataclass(frozen=True)
class Node:
    """One decomposition node: its bag B_u and edge cover (guard) lambda_u."""

    id: NodeId
    bag: VertexSet
    cover: EdgeSet
    label: str | None = None


class GhdSpec(TypedDict):
    """Plain-data description of a rooted GHD (used by fixtures).

    ``nodes`` maps a label to (bag vertices, cover edge names); ``children`` maps a label to
    its children's labels (in order); ``root`` is a label.
    """

    root: str
    nodes: Mapping[str, tuple[Iterable[Vertex], Iterable[EdgeName]]]
    children: Mapping[str, Sequence[str]]


class GHD:
    """A rooted decomposition tree with bags and covers (paper §2.2, D6-D8)."""

    __slots__ = ("_nodes", "_parent", "_children", "_label_index", "_root", "_next_id")

    def __init__(self) -> None:
        """An empty tree (no nodes, no root)."""
        self._nodes: dict[NodeId, Node] = {}
        self._parent: dict[NodeId, NodeId | None] = {}
        self._children: dict[NodeId, list[NodeId]] = {}
        self._label_index: dict[str, NodeId] = {}
        self._root: NodeId | None = None
        self._next_id: NodeId = 0

    # --- spec conversion ----------------------------------------------------------------
    @classmethod
    def from_spec(cls, spec: GhdSpec) -> "GHD":
        """Build from a GhdSpec; raises InvalidGHDError if it is not a tree.

        Ids are assigned in preorder from the root, following the children order (root = 0).
        Bags/covers given as strings are iterated character-wise ("cehik" -> {c,e,h,i,k}).
        """
        try:
            root_label = spec["root"]
            nodes = spec["nodes"]
        except (KeyError, TypeError) as exc:
            raise InvalidGHDError(f"GhdSpec lacks 'root' or 'nodes': {exc!r}") from exc
        children_spec: Mapping[str, Sequence[str]] = spec.get("children", {}) or {}
        if root_label not in nodes:
            raise InvalidGHDError(f"spec root {root_label!r} is not a node label")

        parent_of: dict[str, str] = {}
        for p, kids in children_spec.items():
            if p not in nodes:
                raise InvalidGHDError(f"spec children entry for unknown node label {p!r}")
            if isinstance(kids, str):
                raise InvalidGHDError(f"children of {p!r} must be a sequence of labels, not the string {kids!r}")
            for c in kids:
                if c not in nodes:
                    raise InvalidGHDError(f"spec node {p!r} has unknown child label {c!r}")
                if c == root_label:
                    raise InvalidGHDError(f"spec root {c!r} is listed as a child of {p!r} (cycle)")
                if c in parent_of:
                    raise InvalidGHDError(
                        f"spec node {c!r} has two parents ({parent_of[c]!r} and {p!r})")
                parent_of[c] = p

        order: list[str] = []
        seen: set[str] = {root_label}
        stack = [root_label]
        while stack:
            x = stack.pop()
            order.append(x)
            for c in reversed(list(children_spec.get(x, ()))):
                if c in seen:  # pragma: no cover - excluded by the two-parents/root checks above
                    raise InvalidGHDError(f"spec node {c!r} is reached twice (cycle)")
                seen.add(c)
                stack.append(c)

        unreachable = [lbl for lbl in nodes if lbl not in seen]
        if unreachable:
            first = unreachable[0]
            chain: list[str] = [first]
            cur = first
            while cur in parent_of:
                cur = parent_of[cur]
                if cur in chain:
                    raise InvalidGHDError(f"spec contains a cycle through node {cur!r}")
                chain.append(cur)
            raise InvalidGHDError(f"spec nodes {sorted(unreachable)!r} are not reachable from root {root_label!r}")

        g = cls()
        ids: dict[str, NodeId] = {}
        for lbl in order:
            entry = nodes[lbl]
            try:
                bag, cover = entry
            except (TypeError, ValueError) as exc:
                raise InvalidGHDError(f"spec node {lbl!r} must be a (bag, cover) pair, got {entry!r}") from exc
            parent_label = parent_of.get(lbl)
            ids[lbl] = g.add_node(bag, cover, parent=None if parent_label is None else ids[parent_label],
                                  label=lbl)
        return g

    def to_spec(self) -> GhdSpec:
        """Inverse of from_spec. Unlabelled nodes get the label ``f"#{id}"``.

        Bags and covers are emitted as sorted tuples; every node has a ``children`` entry.
        """
        root = self.root
        labels: dict[NodeId, str] = {}
        used: set[str] = set()
        for nid in self.node_ids():
            lbl = self._nodes[nid].label
            labels[nid] = lbl if lbl is not None else f"#{nid}"
        for nid, lbl in labels.items():
            if lbl in used:
                raise InvalidGHDError(f"to_spec: generated label {lbl!r} for node {nid} collides with an existing label")
            used.add(lbl)
        nodes: dict[str, tuple[tuple[Vertex, ...], tuple[EdgeName, ...]]] = {}
        children: dict[str, list[str]] = {}
        for nid in self.preorder(root):
            n = self._nodes[nid]
            nodes[labels[nid]] = (tuple(sorted(n.bag)), tuple(sorted(n.cover)))
            children[labels[nid]] = [labels[c] for c in self._children[nid]]
        return GhdSpec(root=labels[root], nodes=nodes, children=children)

    # --- construction -----------------------------------------------------------------
    def add_node(self, bag: Iterable[Vertex], cover: Iterable[EdgeName], *,
                 parent: NodeId | None = None, label: str | None = None) -> NodeId:
        """Add a node; the first node added without a parent becomes the root.

        A parentless node is only allowed while the tree is empty. Children are kept in
        insertion order. Returns the new node's id.
        """
        if parent is None:
            if self._nodes:
                raise InvalidGHDError(
                    f"node {label!r} added without a parent, but the tree already has root {self._root}")
        elif parent not in self._nodes:
            raise InvalidGHDError(f"unknown parent node {parent} for new node {label!r}")
        if label is not None and label in self._label_index:
            raise InvalidGHDError(f"duplicate node label {label!r} (already node {self._label_index[label]})")
        nid = self._next_id
        self._insert(nid, frozenset(bag), frozenset(cover), label, parent)
        return nid

    def _insert(self, nid: NodeId, bag: VertexSet, cover: EdgeSet, label: str | None,
                parent: NodeId | None) -> None:
        """Low-level insertion with a given id (callers have checked id/label/parent)."""
        self._nodes[nid] = Node(nid, bag, cover, label)
        self._parent[nid] = parent
        self._children[nid] = []
        if parent is None:
            self._root = nid
        else:
            self._children[parent].append(nid)
        if label is not None:
            self._label_index[label] = nid
        if nid >= self._next_id:
            self._next_id = nid + 1

    def set_labels(self, node: NodeId, *, bag: Iterable[Vertex] | None = None,
                   cover: Iterable[EdgeName] | None = None) -> None:
        """Replace a node's bag and/or cover (used only by the DelVar fast path and normalisers)."""
        n = self.node(node)
        changes: dict[str, frozenset[str]] = {}
        if bag is not None:
            changes["bag"] = frozenset(bag)
        if cover is not None:
            changes["cover"] = frozenset(cover)
        if changes:
            self._nodes[node] = dataclasses.replace(n, **changes)

    def copy(self) -> "GHD":
        """Deep copy preserving ids, labels, root and children order."""
        g = GHD()
        g._nodes = dict(self._nodes)  # Node objects are immutable, so sharing them is safe
        g._parent = dict(self._parent)
        g._children = {k: list(v) for k, v in self._children.items()}
        g._label_index = dict(self._label_index)
        g._root = self._root
        g._next_id = self._next_id
        return g

    # --- access -------------------------------------------------------------------------
    @property
    def root(self) -> NodeId:
        """The current root (rooting is extra structure, D8)."""
        if self._root is None:
            raise InvalidGHDError("empty GHD has no root")
        return self._root

    def node(self, node: NodeId) -> Node:
        """The Node (bag B_u, cover lambda_u) with this id."""
        try:
            return self._nodes[node]
        except (KeyError, TypeError):
            raise InvalidGHDError(f"unknown node id {node!r}") from None

    def node_ids(self) -> list[NodeId]:
        """All node ids in increasing order (deterministic iteration everywhere)."""
        return sorted(self._nodes)

    def by_label(self, label: str) -> NodeId:
        """The id of the node with this label."""
        try:
            return self._label_index[label]
        except (KeyError, TypeError):
            raise InvalidGHDError(f"unknown node label {label!r}") from None

    def parent(self, node: NodeId) -> NodeId | None:
        """Parent under the current root (None for the root)."""
        self._check(node)
        return self._parent[node]

    def children(self, node: NodeId) -> tuple[NodeId, ...]:
        """Children under the current root, in order."""
        self._check(node)
        return tuple(self._children[node])

    def tree_neighbors(self, node: NodeId) -> tuple[NodeId, ...]:
        """Parent (if any) and children: adjacency in the unrooted tree."""
        self._check(node)
        p = self._parent[node]
        kids = tuple(self._children[node])
        return kids if p is None else (p, *kids)

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self) -> Iterator[Node]:
        """The Node objects in increasing id order."""
        for nid in self.node_ids():
            yield self._nodes[nid]

    def __repr__(self) -> str:
        if not self._nodes:
            return "GHD(<empty>)"
        def name(i: NodeId) -> str:
            lbl = self._nodes[i].label
            return f"{i}:{lbl}" if lbl is not None else str(i)
        edges = ", ".join(f"{name(self._parent[i])}-{name(i)}"  # type: ignore[arg-type]
                          for i in self.preorder() if self._parent[i] is not None)
        return f"GHD(root={name(self.root)}, n={len(self)}, edges=[{edges}])"

    def _check(self, node: NodeId) -> None:
        if node not in self._nodes:
            raise InvalidGHDError(f"unknown node id {node!r}")

    def _check_set(self, nodes: Iterable[NodeId]) -> frozenset[NodeId]:
        s = frozenset(nodes)
        unknown = [n for n in s if n not in self._nodes]
        if unknown:
            raise InvalidGHDError(f"unknown node ids {sorted(unknown, key=repr)!r}")
        return s

    # --- traversal and queries ------------------------------------------------------------
    def preorder(self, start: NodeId | None = None) -> list[NodeId]:
        """Preorder of T_start (default: the whole tree), children in order. Iterative."""
        if start is None:
            if not self._nodes:
                return []
            start = self.root
        self._check(start)
        out: list[NodeId] = []
        stack = [start]
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(reversed(self._children[x]))
        return out

    def postorder(self, start: NodeId | None = None) -> list[NodeId]:
        """Postorder of T_start (default: the whole tree), children in order. Iterative."""
        if start is None:
            if not self._nodes:
                return []
            start = self.root
        self._check(start)
        # Reverse of a preorder that visits children right-to-left.
        out: list[NodeId] = []
        stack = [start]
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(self._children[x])
        out.reverse()
        return out

    def subtree_nodes(self, node: NodeId) -> frozenset[NodeId]:
        """Node set of T_u (the subtree rooted at u, under the current root; D8)."""
        return frozenset(self.preorder(node))

    def ancestors(self, node: NodeId) -> list[NodeId]:
        """From the parent up to the root."""
        self._check(node)
        out: list[NodeId] = []
        p = self._parent[node]
        while p is not None:
            out.append(p)
            p = self._parent[p]
        return out

    def is_connected(self, nodes: Iterable[NodeId]) -> bool:
        """True iff ``nodes`` induces a connected subtree (the empty set counts as connected).

        Used for subtrees T' (Def 4.1) and for vertex occurrence sets (GHD condition (2)).
        """
        s = self._check_set(nodes)
        if not s:
            return True
        start = next(iter(s))
        seen = {start}
        stack = [start]
        while stack:
            for y in self._neighbors_in(stack.pop(), s):
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        return len(seen) == len(s)

    def _neighbors_in(self, x: NodeId, s: frozenset[NodeId] | set[NodeId]) -> Iterator[NodeId]:
        p = self._parent[x]
        if p is not None and p in s:
            yield p
        for c in self._children[x]:
            if c in s:
                yield c

    def leaves_of(self, nodes: Iterable[NodeId]) -> list[NodeId]:
        """Leaves of the subtree induced by ``nodes`` (degree <= 1 inside it), sorted (Alg 2 line 5)."""
        s = self._check_set(nodes)
        return sorted(x for x in s if sum(1 for _ in self._neighbors_in(x, s)) <= 1)

    def bag_union(self, nodes: Iterable[NodeId]) -> VertexSet:
        """B(T') = union of the bags of ``nodes`` (paper §4.1)."""
        s = self._check_set(nodes)
        return frozenset().union(*(self._nodes[x].bag for x in s))

    def width(self) -> int:
        """max |lambda_u| (paper §2.2); 0 for an empty tree."""
        return max((len(n.cover) for n in self._nodes.values()), default=0)

    # --- restructuring --------------------------------------------------------------------
    def reroot(self, node: NodeId) -> None:
        """Make ``node`` the root; the unrooted tree is unchanged.

        Parent pointers along the path node -> old root are reversed. Existing children
        order is kept, and each former parent is appended at the end of its new parent's list.
        """
        self._check(node)
        x = node
        p = self._parent[x]
        while p is not None:
            pp = self._parent[p]
            self._children[p].remove(x)
            self._children[x].append(p)
            self._parent[p] = x
            x, p = p, pp
        self._parent[node] = None
        self._root = node

    def components_without(self, removed: Iterable[NodeId]) -> list[frozenset[NodeId]]:
        """Node sets of the trees of the forest T \\ T' (D17), sorted by smallest id."""
        r = self._check_set(removed)
        rest = set(self._nodes) - r
        comps: list[frozenset[NodeId]] = []
        for start in sorted(rest):
            if start not in rest:
                continue
            rest.discard(start)
            comp = [start]
            queue = deque([start])
            while queue:
                x = queue.popleft()
                for y in self._neighbors_in(x, rest):
                    rest.discard(y)
                    comp.append(y)
                    queue.append(y)
            comps.append(frozenset(comp))
        return comps  # built from starts in increasing order, so already sorted by smallest id

    def extract(self, nodes: Iterable[NodeId], root: NodeId) -> "GHD":
        """The connected node set as a separate GHD rooted at ``root`` (ids and labels kept).

        Contains exactly the tree edges among ``nodes``; used to cut T* and the outer trees
        of T \\ T* (D17, Theorem 4.5) out of a GHD.
        """
        s = self._check_set(nodes)
        if root not in s:
            raise InvalidGHDError(f"extract: root {root!r} is not in the node set")
        if not self.is_connected(s):
            raise InvalidGHDError(f"extract: node set {sorted(s)!r} is not connected")
        # The topmost node of s under the current root (unique, as s is connected).
        top = root
        while self._parent[top] is not None and self._parent[top] in s:
            top = self._parent[top]  # type: ignore[assignment]
        g = GHD()
        for x in self._preorder_within(top, s):
            n = self._nodes[x]
            g._insert(x, n.bag, n.cover, n.label, None if x == top else self._parent[x])
        g.reroot(root)
        return g

    def _preorder_within(self, start: NodeId, s: frozenset[NodeId]) -> list[NodeId]:
        """Preorder of T_start restricted to descendants reachable inside ``s`` (helper)."""
        out: list[NodeId] = []
        stack = [start]
        while stack:
            x = stack.pop()
            out.append(x)
            stack.extend(c for c in reversed(self._children[x]) if c in s)
        return out

    def attach(self, at: NodeId, other: "GHD", other_node: NodeId) -> dict[NodeId, NodeId]:
        """Glue: re-root ``other`` at ``other_node`` and hang it below ``at`` by one tree edge.

        Returns the id map other-id -> new id (fresh ids are allocated on collision).
        This is the primitive behind Theorem 4.5's re-attachment of outer subtrees.

        Ids of ``other`` not used in ``self`` are kept; colliding ids get fresh ids
        max(ids of self and other) + 1, +2, ... in preorder of the rerooted ``other``.
        ``other`` is not modified; on a label collision ``self`` is not modified either.
        """
        self._check(at)
        other._check(other_node)
        o = other.copy()
        o.reroot(other_node)
        clashes = sorted(lbl for lbl in o._label_index if lbl in self._label_index)
        if clashes:
            raise InvalidGHDError(f"attach: labels {clashes!r} already exist in the target GHD")
        order = o.preorder()
        fresh = max(self._next_id, o._next_id)
        mapping: dict[NodeId, NodeId] = {}
        for x in order:
            if x in self._nodes:
                mapping[x] = fresh
                fresh += 1
            else:
                mapping[x] = x
        for x in order:
            n = o._nodes[x]
            p = o._parent[x]
            self._insert(mapping[x], n.bag, n.cover, n.label, at if p is None else mapping[p])
        return mapping

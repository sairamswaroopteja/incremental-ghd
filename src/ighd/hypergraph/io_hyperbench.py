"""HyperBench text format (stage S1; used by benchmarks S14).

Format: a comma-separated list of ``name(v1,v2,...)`` terms, optionally ending with ``.``;
whitespace, newlines and ``%`` comment lines are ignored.

Names are permissive: any characters except ``(``, ``)``, ``,`` and whitespace. A single
``.`` after the last term is the terminator and is stripped.
"""

from __future__ import annotations

import re

from ighd.common.errors import InvalidHypergraphError
from ighd.common.types import EdgeName, Vertex
from ighd.hypergraph.core import Hypergraph

_WS = re.compile(r"\s+")
_FORBIDDEN = re.compile(r"[(),\s]")


def _strip_comments(text: str) -> str:
    """Drop every line whose first non-space character is ``%``."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("%"))


def _fragment(s: str, i: int, width: int = 30) -> str:
    return s[max(0, i - width // 2): i + width // 2]


def parse_hyperbench(text: str) -> Hypergraph:
    """Parse HyperBench text. Raises InvalidHypergraphError with the offending term on bad input."""
    body = _WS.sub("", _strip_comments(text))
    if body.endswith(".") and (body == "." or body[-2] == ")"):
        body = body[:-1]
    edges: dict[EdgeName, list[Vertex]] = {}
    i, n = 0, len(body)
    while i < n:
        open_at = body.find("(", i)
        if open_at < 0:
            raise InvalidHypergraphError(f"term without '(' near {body[i:i + 30]!r}")
        name = body[i:open_at]
        if not name:
            raise InvalidHypergraphError(f"term without an edge name near {_fragment(body, open_at)!r}")
        if ")" in name or "," in name:
            raise InvalidHypergraphError(f"unbalanced parentheses or stray ',' near {name!r}")
        close_at = body.find(")", open_at + 1)
        if close_at < 0:
            raise InvalidHypergraphError(f"unbalanced parentheses: unclosed term {body[i:i + 30]!r}")
        inner = body[open_at + 1:close_at]
        term = body[i:close_at + 1]
        if "(" in inner:
            raise InvalidHypergraphError(f"unbalanced parentheses in term {term!r}")
        if not inner:
            raise InvalidHypergraphError(f"edge {name!r} has no vertices: {term!r}")
        vertices = inner.split(",")
        if any(not v for v in vertices):
            raise InvalidHypergraphError(f"empty vertex name in term {term!r}")
        if name in edges:
            raise InvalidHypergraphError(f"duplicate edge name {name!r} in term {term!r}")
        edges[name] = vertices
        i = close_at + 1
        if i < n:
            if body[i] != ",":
                raise InvalidHypergraphError(f"expected ',' after term {term!r}, found {body[i:i + 30]!r}")
            i += 1
            if i == n:
                raise InvalidHypergraphError(f"trailing ',' after term {term!r}")
    return Hypergraph(edges)


def _check_name(kind: str, name: str) -> None:
    if not name or _FORBIDDEN.search(name):
        raise InvalidHypergraphError(f"{kind} name {name!r} cannot be written in HyperBench format")


def to_hyperbench(h: Hypergraph) -> str:
    """Serialise with edges in name order; ``parse_hyperbench(to_hyperbench(h)) == h``.

    One term per line, joined by ``",\\n"``, ending with ``"."``. Raises InvalidHypergraphError
    if a name contains ``(``, ``)``, ``,`` or whitespace, is empty, or (edge names) starts with
    ``%`` — such names would not survive a round trip.
    """
    lines: list[str] = []
    for name in sorted(h.edge_names):
        _check_name("edge", name)
        if name.startswith("%"):
            raise InvalidHypergraphError(f"edge name {name!r} would be read as a comment")
        vs = sorted(h.edge(name))
        for v in vs:
            _check_name("vertex", v)
        lines.append(f"{name}({','.join(vs)})")
    return ",\n".join(lines) + "."

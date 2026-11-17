"""HyperBench instance enumeration with the statistics the §6.1 generator needs.

Data files are untrusted input: they are only read as text and parsed by
``ighd.hypergraph.parse_hyperbench``; nothing from the data folder is ever executed.

Family = the leading run of letters of the file name (``Kakuro-easy-...`` -> ``Kakuro``), with
``rand_q...`` (HyperBench's random conjunctive queries) kept apart from the random CSPs
``rand-...``. A name without leading letters (``2bitcomp_5``) gets the family ``other``.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from ighd.hypergraph import Hypergraph, parse_hyperbench

_FAMILY = re.compile(r"^[A-Za-z]+")


def family_of(name: str) -> str:
    """Instance family from a HyperBench file name (see module docstring)."""
    if name.startswith("rand_q"):
        return "rand_q"
    m = _FAMILY.match(name)
    return m.group(0) if m else "other"


@dataclass(frozen=True)
class InstanceInfo:
    """One HyperBench instance and its size statistics.

    avg_degree = sum_e |e| / |V| (mean number of edges per vertex);
    avg_rank   = sum_e |e| / |E| (mean edge size); rank = max |e|.
    """

    name: str
    path: str
    family: str
    n_vertices: int
    n_edges: int
    rank: int
    avg_degree: float
    avg_rank: float

    def to_dict(self) -> dict:
        return asdict(self)


def stats(h: Hypergraph) -> tuple[int, int, int, float, float]:
    """(|V|, |E|, rank, avg degree, avg rank) of ``h``; averages are 0 for an empty hypergraph."""
    nv, ne = len(h.vertices), len(h.edge_names)
    incidences = sum(len(vs) for vs in h.edges.values())
    rank = max((len(vs) for vs in h.edges.values()), default=0)
    return nv, ne, rank, (incidences / nv if nv else 0.0), (incidences / ne if ne else 0.0)


def instance_info(path: Path, h: Hypergraph | None = None) -> InstanceInfo:
    if h is None:
        h = load(path)
    nv, ne, rank, avg_deg, avg_rank = stats(h)
    return InstanceInfo(path.name, str(path), family_of(path.name), nv, ne, rank, avg_deg, avg_rank)


def load(path: Path | str) -> Hypergraph:
    """Parse one HyperBench file (read as UTF-8 text; never executed)."""
    return parse_hyperbench(Path(path).read_text(encoding="utf-8", errors="strict"))


def ceil_avg_degree(info: InstanceInfo) -> int:
    """⌈avg degree⌉ with a tolerance for float noise (e.g. 2.0000000001 -> 2)."""
    return max(1, math.ceil(round(info.avg_degree, 9)))


def ceil_avg_rank(info: InstanceInfo) -> int:
    return max(1, math.ceil(round(info.avg_rank, 9)))


def _index(data_dir: Path, cache_file: Path | None) -> list[InstanceInfo]:
    """Statistics of every ``*.hg`` file, cached by (name, size, mtime) because parsing all 3000
    HyperBench files takes 10-20 s."""
    files = sorted(data_dir.glob("*.hg"))
    cached: dict[str, dict] = {}
    if cache_file is not None and cache_file.exists():
        try:
            cached = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
    out, fresh, changed = [], {}, False
    for f in files:
        st = f.stat()
        key = f"{f.name}|{st.st_size}|{st.st_mtime_ns}"
        row = cached.get(key)
        if row is None:
            row = instance_info(f).to_dict()
            changed = True
        row = dict(row, path=str(f))
        fresh[key] = row
        out.append(InstanceInfo(**row))
    if cache_file is not None and (changed or len(fresh) != len(cached)):
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(fresh), encoding="utf-8")
    return out


def enumerate_instances(
    data_dir: Path | str,
    *,
    families: list[str] | None = None,
    min_vertices: int = 0,
    max_vertices: int | None = None,
    max_edges: int | None = None,
    names: list[str] | None = None,
    cache_file: Path | None = None,
) -> list[InstanceInfo]:
    """Instances in ``data_dir`` that pass the filters, sorted by name.

    ``families`` matches :func:`family_of` case-sensitively; ``names`` restricts to exact file names.
    """
    data_dir = Path(data_dir)
    if not data_dir.is_dir():
        raise FileNotFoundError(f"HyperBench data folder not found: {data_dir}")
    fams = set(families) if families else None
    wanted = set(names) if names else None
    out = []
    for info in _index(data_dir, cache_file):
        if fams is not None and info.family not in fams:
            continue
        if wanted is not None and info.name not in wanted:
            continue
        if info.n_vertices < min_vertices:
            continue
        if max_vertices is not None and info.n_vertices > max_vertices:
            continue
        if max_edges is not None and info.n_edges > max_edges:
            continue
        out.append(info)
    return out

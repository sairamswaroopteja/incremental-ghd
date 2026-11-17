# incremental-ghd

A research implementation of Gottlob, Lanzinger, Longo and Okulmus, *Incremental Updates of Generalized Hypertree Decompositions* (arXiv:2209.10375).

Given a hypergraph H, a GHD of H of minimum width k and a modification δ (one of the six classes AddVar, DelVar, AddConstr, DelConstr, AddEq and DelEq, or a sequence of them), `ghd_update` returns one of three answers:
- a validated GHD of δ(H) of width ≤ k;
- `PROVEN_NO`: an exact proof that no such GHD exists;
- `NOT_FOUND`: no GHD was found, and nonexistence is not established (heuristic or budgeted search only).

**Status:** stages S0–S15 are complete. Read `docs/FINAL_REPORT.md` first. It separates exact, heuristic, proven and empirical results, and lists the paper errors found and the known limitations.

## Requirements

Python 3.11 or newer, with `pytest` and `hypothesis`. The benchmarks additionally need `matplotlib`, `numpy`, `pandas` and `psutil`. There is nothing to install: tests and examples use `src/` directly.

## Quick start

```bash
python examples/quickstart.py
```

```python
from ighd.common import DecomposerMode
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr
from ighd.static import ghw_by_search
from ighd.update import Strategy, ghd_update

h = Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd", "e4": "da"})
k, ghd, _ = ghw_by_search(h, DecomposerMode.EXACT)       # k = ghw(H) = 2
r = ghd_update(h, ghd, AddConstr("f", frozenset("bd")), strategy=Strategy.PAPER)
print(r.status, r.width, r.trace.reused_nodes, r.trace.notes)
```

Strategies:
- `PAPER`: Algorithm 2, then scenes (Algorithms 3–4), then DecompUpdate (Algorithm 5).
- `THEOREM45`: Algorithm 2, then δ(H)\*, bag constraints and gluing.
- `RECOMPUTE`: the paper's "Classic".

Paper-reading switches are in `ighd.common.config.Semantics`. Defaults: `PAPER_DEFAULT`, see `FAITHFULNESS_LEDGER.md`.

## Tests

```bash
python -m pytest
```

That is the default suite: 691 tests, about 1–2 min. The slow suite takes about 6 min and includes the 10⁴-step randomized criterion:

```bash
python -m pytest -m slow
```

To run only the tests that pin paper discrepancies:

```bash
python -m pytest -m paper_discrepancy
```

## Benchmarks (HyperBench, Update vs Classic)

The data is not in the repository. Put HyperBench's `.hg` files in `benchmarks/data/hyperbench/all/`. They come from the "Download All" archive at http://hyperbench.dbai.tuwien.ac.at.

```bash
python -m benchmarks.run --preset smoke
```

```bash
python -m benchmarks.run --preset small --seed 0
```

Results go to `benchmarks/results/<run-id>/`. See `benchmarks/README.md` for options, metric definitions and the honesty notes: absolute numbers are not comparable with the paper.

## Layout

| Path | Contents |
|---|---|
| `src/ighd/` | `hypergraph`, `modifications`, `ghd` (tree, validator, normal form), `oracle`, `static` (separation, decomposer), `mutable` (Algorithm 2), `constraints` (Theorem 4.5), `scenes` (Algorithms 3–4), `update` (Algorithm 5, pipeline), `testing` (generators), `common` |
| `tests/` | `unit/`, `paper_examples/`, `integration/`, `dynamic_updates/`, `randomized/`, `benchmarks/`, `fixtures/` |
| `benchmarks/` | HyperBench loader, §6.1 generator, runner, metrics, plots |
| `examples/` | runnable examples |

## Documents

| Document | Contents |
|---|---|
| `docs/FINAL_REPORT.md` | verdict, feature and guarantee matrix, paper issues, benchmarks, limitations |
| `docs/PAPER_ANALYSIS.md` | definitions, results, the algorithms read line by line, ambiguities A1–A29 |
| `docs/MATHEMATICAL_INVARIANTS.md` | invariants I1–I10, and our proofs: Lemmas A–H and Theorem E |
| `docs/TESTING_REPORT.md` | testing levels, traceability, measured results, limitations |
| `docs/ARCHITECTURE.md` | public interfaces and the pipeline |
| `docs/IMPLEMENTATION_PLAN.md` | the original plan, stages S0–S15 |
| `FAITHFULNESS_LEDGER.md` | every reading of, or departure from, the paper, with its pinning test |
| `PROGRESS.md` | stage tracker |

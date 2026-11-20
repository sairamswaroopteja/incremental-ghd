# incremental-ghd

A research implementation of Gottlob, Lanzinger, Longo and Okulmus, *Incremental Updates of Generalized Hypertree Decompositions* (arXiv:2209.10375).

Given a hypergraph H, a GHD of H of minimum width k and a modification δ (one of the six classes AddVar, DelVar, AddConstr, DelConstr, AddEq and DelEq, or a sequence of them), `ghd_update` returns one of three answers:
- a validated GHD of δ(H) of width ≤ k;
- `PROVEN_NO`: an exact proof that no such GHD exists;
- `NOT_FOUND`: no GHD was found, and nonexistence is not established (heuristic or budgeted search only).

**Status:** stages S0–S15 are complete. Read `docs/FINAL_REPORT.md` first. It separates exact, heuristic, proven and empirical results, and lists the paper errors found and the known limitations.

## Requirements

Python 3.11 or newer, with `pytest` and `hypothesis`. The benchmarks additionally need `matplotlib`, `numpy`, `pandas` and `psutil`. There is nothing to install: tests and examples use `src/` directly.

## Web interface (easiest)

```bash
python web.py
```

This opens http://127.0.0.1:8765 in your browser. The server runs only on your machine and uses only the Python standard library. In the page:

1. **Initial hypergraph.** Type it as one edge per line (`e1: a b c`), or use HyperBench syntax. You can also pick a built-in example or a small HyperBench instance, or upload a `.hg` file. Then press **Decompose**.
2. **Apply a modification.** Choose one of the six buttons: Add vertex, Delete vertex, Add edge, Delete edge, Merge vertices or Split vertex. Each has a form filled with your current vertices and edges: tick edges, pick vertices, or assign edges to the parts of a split. A preview shows the modification before you press **Apply**.
3. **Output after each step:**
   - the current ghw, marked *proven* or *upper bound*;
   - what the update did: ghw rose, dropped or stayed, how many old decomposition nodes were kept, and the time taken;
   - a drawing of the hypergraph in which every edge is a coloured shape drawn around exactly its vertices; edges changed by the last step have a dashed, thicker outline and a ● mark. Hovering an edge, a vertex or a decomposition node highlights what belongs to it, and clicking vertices or edges fills in the current form;
   - a drawing of the decomposition (bags B and covers λ), with kept nodes in blue and new nodes in orange;
   - a log of every step.

   **Undo** and **New hypergraph** are in the header.
4. **Settings:**
   - the update method: the paper's Algorithm 5, Theorem 4.5, or recompute;
   - exact ghw tracking;
   - an oracle cross-check;
   - a time limit per search. It defaults to 30 s; leave it empty for none. A step that hits the limit says so and is never shown as proven.

### Hosting it (Render)

`render.yaml` is a Render Blueprint: in Render choose **New → Blueprint**, connect this repository, and Render runs `python web.py --public` with Python 3.12 and a `/healthz` health check. Public mode differs from local mode in three ways:
- **Sessions:** each visitor gets a private session, identified by a random, HttpOnly cookie. At most 200 sessions are kept, and a session idle for an hour is dropped.
- **Limits:** inputs may have at most 60 edges and 60 vertices. Every search has a time limit, 10 s by default and at most 20 s, because the exact search is exponential.
- **Network:** the server listens on `0.0.0.0` and on the port in `$PORT`.

Render's free plan sleeps when idle, so the first visit after a pause takes about a minute.

## Online, query-based use from a terminal

```bash
python online.py
```

You type the initial hypergraph, then send modifications one at a time. Each one is applied incrementally to the current decomposition when you type it, and you can query the state in between:

```
ghd> edge e1 a b
ghd> e2(b,c), e3(c,d).
ghd> start                       # exact minimum-width decomposition of the initial hypergraph
ghd> addconstr e4 d a            # online modification: ghw rises 1 -> 2, reported and proven
ghd> addvar x e1 e3
ghd> addeq b c -> b
ghd> deleq b : b = e1 e2 ; c = e2 e3
ghd> ghw                         # query: current ghw, and whether it is proven
ghd> ghd                         # query: current decomposition
ghd> check | history | show | undo | help
```

- **Commands.** The six modifications are `addvar`, `delvar`, `addconstr`, `delconstr`, `addeq` and `deleq`. Queries are `ghw`, `ghd`, `show`, `check` and `history`. Settings are `strategy`, `tighten`, `oracle` and `timeout`. Type `help` for the full syntax.
- **Other ways to start.** `--load file.hg` starts from a HyperBench file. `--script cmds.txt` replays a command file; `examples/online_session.txt` is an example.
- **What is exact.** Each modification goes through the paper's update (Algorithm 5 by default). Reporting ghw itself after every step needs extra exact searches, which are our addition, not the paper's:
  - when the update proves the old width impossible, the system searches upward;
  - when a modification could lower ghw, it checks one width smaller.
- **Without a time limit**, every reported ghw is proven. A step that hits a `timeout` says so, and is never presented as proven.

## Quick start (library)

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

That is the default suite: 708 tests, about 1–2 min. The slow suite takes about 6 min and includes the 10⁴-step randomized criterion:

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
| `web.py`, `online.py`, `src/ighd/online/` | the web interface and the terminal version of the online system (`OnlineSession`, `Shell`, `web` + `static/index.html`) |
| `src/ighd/` | `hypergraph`, `modifications`, `ghd` (tree, validator, normal form), `oracle`, `static` (separation, decomposer), `mutable` (Algorithm 2), `constraints` (Theorem 4.5), `scenes` (Algorithms 3–4), `update` (Algorithm 5, pipeline), `testing` (generators), `common` |
| `tests/` | `unit/`, `paper_examples/`, `integration/`, `dynamic_updates/`, `randomized/`, `online/`, `benchmarks/`, `fixtures/` |
| `benchmarks/` | HyperBench loader, §6.1 generator, runner, metrics, plots |
| `examples/` | `quickstart.py`, `walkthrough.py` (paper Ex. 4.3/5.2 step by step), `modifications_tour.py` (ghw over a chain of edits, with a picture), `online_session.txt` |

## Documents

| Document | Contents |
|---|---|
| `docs/CODE_WALKTHROUGH.md` | how the code is organised: which file implements which algorithm, the call order of one update, and a real trace of paper Example 4.3/5.2 |
| `docs/FINAL_REPORT.md` | verdict, feature and guarantee matrix, paper issues, benchmarks, limitations |
| `docs/PAPER_ANALYSIS.md` | definitions, results, the algorithms read line by line, ambiguities A1–A29 |
| `docs/MATHEMATICAL_INVARIANTS.md` | invariants I1–I10, and our proofs: Lemmas A–H and Theorem E |
| `docs/TESTING_REPORT.md` | testing levels, traceability, measured results, limitations |
| `docs/ARCHITECTURE.md` | public interfaces and the pipeline |
| `docs/IMPLEMENTATION_PLAN.md` | the original plan, stages S0–S15 |
| `FAITHFULNESS_LEDGER.md` | every reading of, or departure from, the paper, with its pinning test |
| `PROGRESS.md` | stage tracker |

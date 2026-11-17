# Benchmarks (stage S14): the paper's §6 comparison protocol

This folder reproduces the **comparison protocol** of Gottlob, Lanzinger, Longo, Okulmus,
*Incremental Updates of Generalized Hypertree Decompositions* (arXiv 2209.10375), §6:
for HyperBench hypergraphs H with a minimum-width GHD and random §6.1 modifications δ, compare

- **Update** = `ghd_update(H, GHD, δ, strategy=Strategy.PAPER)` (Algorithms 2–5: scenes +
  DecompUpdate + decomposer), and
- **Classic** = `ghd_update(H, GHD, δ, strategy=Strategy.RECOMPUTE)` (the same decomposer on δ(H)
  from scratch),

with the same decomposer type (`TopDownDecomposer`) and mode, the same width bound k (the input
GHD's width) and the same time limit.

**It does not reproduce the paper's absolute numbers, and they are not comparable.** Our
decomposer is a pure-Python, memoised top-down search (`ighd.static.TopDownDecomposer`), not
BalancedGo / log-k-decomp; the machine differs; and our limits are seconds, not the paper's
30 min / 1 GB. Treat every number as a property of *this* implementation on *this* machine.

## Data

HyperBench, <http://hyperbench.dbai.tuwien.ac.at>, "Download All" (3000 `.hg` files), extracted
flat into `benchmarks/data/hyperbench/all/`. `benchmarks/data/` and `benchmarks/results/` are
git-ignored. The files are untrusted input: they are only read as text and parsed with
`ighd.hypergraph.parse_hyperbench`; nothing in that folder is executed, and no command uses it as
working directory. The paper uses the 1798 of 2035 instances with known optimal ghw; we instead
establish ghw ourselves per instance (below) and exclude instances where we cannot.

## Running

From the project root (no install needed; `benchmarks/__init__.py` puts `src/` on `sys.path`):

```
python -m benchmarks.run --preset smoke                 # ~20-60 s
python -m benchmarks.run --preset small --seed 0        # the reproducible subset (see below)
python -m benchmarks.run --preset small --seed 0 --modes exact,heuristic --run-id small-both
python -m benchmarks.run --families Kakuro,Nonogram --max-vertices 50 --limit 30 --timeout 30 --jobs 8
python -m pytest tests/benchmarks                        # fast tests of generator, metrics, runner, pool
```

| option | meaning |
|---|---|
| `--preset {smoke,small,full}` (alias `--subset`) | parameter bundle; explicit options override it |
| `--seed` | seeds the instance sample and every modification draw |
| `--per-class` | modifications per class per instance (paper: 5) |
| `--timeout` | seconds per single Update or Classic run |
| `--prep-timeout` | seconds for the EXACT ghw search that establishes k |
| `--jobs` | parallel worker processes (default: physical cores) |
| `--mem-cap-mb` | sampled RSS cap per worker (default 1024; `0` disables) |
| `--modes exact,heuristic` | decomposer modes; each mode gets its own tables, never mixed |
| `--with-delvar` | also generate DelVar (excluded from the paper's protocol) |
| `--families`, `--names`, `--min-vertices`, `--max-vertices`, `--max-edges` | instance filters |
| `--limit` / `--no-limit` | seeded family-stratified sample size (round-robin over families) |
| `--filter-ms` | the paper's "Classic takes more than 15 ms" filter (default 15) |
| `--run-id`, `--results-dir`, `--overwrite` | output location (default `benchmarks/results/<preset>-seed<seed>/`) |

Presets (`benchmarks/run.py`):

| preset | instances | per class | run limit | ghw-search budget |
|---|---|---|---|---|
| smoke | ≤ 12 vertices, sample of 6 | 2 | 2 s | 5 s |
| small | ≤ 30 vertices, family-stratified sample of 200 (seed-dependent) | 5 | 10 s | 20 s |
| full | everything passing your filters | 5 | 60 s | 120 s |

Measured on the development machine (4 physical / 8 logical cores, 7.7 GB RAM, Windows 11,
Python 3.12, 4 workers): smoke ≈ 20 s; small (seed 0) 1387 s ≈ 23 min, 6710 runs.

## Pipeline

1. **Select** instances (`loader.py`): family (leading letters of the file name; `rand_q` kept
   apart from `rand`), |V|, |E|, rank, avg degree = Σ|e|/|V|, avg rank = Σ|e|/|E|. The index is
   cached in `results/_cache/instance_index.json`.
2. **Establish k and the input GHD** (`worker.prep_task`). The paper needs a *minimum-width*
   input GHD (A14). We run `ghw_by_search(H, EXACT, Budget(prep_timeout))`, which tries
   k = 1, 2, … and returns the first k with a GHD, having refuted every smaller k exhaustively.
   The certificate is recorded per instance:
   - `oracle` — |V| ≤ 16 and the independent DP oracle `exact_ghw(H)` equals k. (This is the check
     `ghd_update(verify_minimality=True)` performs; we do it once per instance in the untimed
     preparation step instead of inside every timed call, because it would add the oracle's
     exponential running time to both systems.) If the search was cut by the budget, the input
     GHD comes from an EXACT search at k = `exact_ghw(H)` only.
   - `exact-search` — the EXACT search found k and was not budget-cut (k − 1 proven impossible).
   - `unknown` — neither; the instance is **excluded** and counted in the summary line
     "skipped: ghw not established". No instance is called optimal without one of the two
     certificates. A mismatch between oracle and search would be recorded as cert `ERROR`.
   The input GHD comes from the EXACT decomposer, so it is in normal form (needed by scenes, A15).
3. **Generate modifications** (`generator.py`, §6.1), five per class, each (seed, instance,
   class) with its own SHA-512-seeded `random.Random`:
   - AddVar: a fresh vertex into ⌈avg degree⌉ distinct random edges (capped at |E|);
   - AddEq: two distinct random vertices x1, x2 merged into x1;
   - DelEq: a random vertex x of degree ≥ 2 split into fresh y1, y2; y1 gets ⌊d/2⌋ of x's edges
     (random), y2 the other ⌈d/2⌉;
   - AddConstr: a new edge on ⌈avg rank⌉ distinct random existing vertices (capped at |V|);
   - DelConstr: a random edge;
   - DelVar only with `--with-delvar`.
   An invalid draw (rejected by the modification class, e.g. DelEq on a degree-1 vertex, or an
   AddConstr scope equal to an existing edge) is redrawn with the same rng; redraws and their
   reasons are recorded in `mods.jsonl` and summarised. If a class is not applicable or 1000
   redraws fail, the slot is recorded as not generated, with the reason. AddEq draws that make two
   existing edges equal are valid (A9: both names kept) and flagged `creates_duplicate_edges`.
4. **Run** (`worker.run_task` in `pool.HardPool`): one task = one system on one
   (instance, modification, mode). A fresh `TopDownDecomposer(mode)` and a fresh
   `Budget(time_limit_s=timeout)` per run; wall time = `perf_counter` around the `ghd_update` call.
   Every UPDATED output, already validated by the pipeline, is **re-validated** in the harness
   with `ighd.ghd.validate` against δ(H) computed independently (`δ.apply(H)`) and width ≤ k; a
   failure becomes status ERROR with "FINDING" in the message.
5. **Metrics, report, plots** (`metrics.py`, `report.py`, `plots.py`).

### Statuses

| status | meaning |
|---|---|
| UPDATED | a GHD of δ(H) of width ≤ k (validated twice) — answer "yes" |
| PROVEN_NO | ghw(δ(H)) > k established by an exhaustive EXACT search — answer "no" |
| NOT_FOUND | the search ended within the limit without an answer (only HEURISTIC can do this) |
| TIMEOUT | no answer within the limit: Budget exhausted (raw NOT_FOUND), the answer arrived after the limit (`raw_status` keeps it), or the pool killed the worker |
| MEMOUT | the RSS watchdog killed the worker, or MemoryError |
| ERROR | exception (message in `error`), worker crash, or a re-validation failure |

A TIMEOUT is never reported as PROVEN_NO: any run whose wall time exceeds the limit is TIMEOUT,
whatever the pipeline returned (and the pipeline itself only reports PROVEN_NO for an EXACT
search that was not budget-cut).

## Metrics (per modification class and overall, separately per decomposer mode)

A *pair* is one (instance, modification, mode) with an Update and a Classic run.

- **Positive %** — per system: yes / (yes + no) over its definite answers; *agreed*: the answer of
  whichever system answered (both, if both did), yes / pairs with an answer. A pair where one
  system says UPDATED and the other PROVEN_NO is a **disagreement**, i.e. a correctness bug; it is
  counted, listed with its reproducer key, and excluded from the agreed answer.
- **Better %** — over pairs where both *finished* (UPDATED / PROVEN_NO / NOT_FOUND within the
  limit): the share where Update's wall time < Classic's.
- **GM U / GM C** — geometric means of the wall times over the same pairs (times floored at 1 µs).
- **GM speed-up** — geometric mean of Classic/Update over the same pairs (> 1: Update faster).
- **Timeouts (A24)** — *exclusive*: pairs where only that system timed out; *total*: all its timeouts.
- **Filter** — the paper reports instances where Classic takes more than 15 ms. We report both
  the unfiltered table and the filtered one (pairs whose Classic wall time, whatever its status,
  exceeds 15 ms).
- Also: MEMOUT, ERROR and NOT_FOUND counts per system, Update outputs in / not in normal form.

EXACT and HEURISTIC results are in separate tables and separate plots. In EXACT mode
"no" answers are proofs; in HEURISTIC mode (`B = B(λ) ∩ (W ∪ conn)` only; sound, incomplete for
ghw) a failure is NOT_FOUND and never "no". HEURISTIC runs therefore have no "no" answers and
their per-system Positive % is 100 whenever defined; read the yes counts together with the
NOT_FOUND column. The input GHD and k are the same (EXACT-established) in both modes.

## Outputs (`benchmarks/results/<run-id>/`)

| file | content |
|---|---|
| `manifest.json` | config (seed, budgets, filters, presets), sha256 over `src/ighd/**/*.py` + `benchmarks/*.py`, machine info, Python and package versions, selected instance list, start/end time, pool kill counts |
| `instances.jsonl` | per instance: statistics, k, certificate, oracle ghw, search time, input GHD spec, notes |
| `mods.jsonl` | every modification slot: spec, description, redraws and reasons, failure |
| `runs.jsonl`, `runs.csv` | one record per run (fields: `runner.RUN_FIELDS`) |
| `summary.md` | instance funnel, correctness checks, the tables (all pairs and Classic > 15 ms) |
| `metrics.json` | the same tables as data |
| `plots/fig7_<mode>.png` | Fig. 7 style: wall time of Update vs Classic by ghw, by |E| (binned), by |V| (binned); pairs where both finished |
| `plots/scatter_<mode>.png` | Classic vs Update wall time, log-log, with the diagonal |

## What is and is not enforced (honesty notes)

- **Time limit: enforced twice.** Inside: the `Budget` time limit, checked at every search
  expansion (the decomposer turns exhaustion into NOT_FOUND). The non-search phases (validation,
  Algorithm 2, scenes, normal-form check) are not budgeted, so a run can overshoot; any overshoot
  is classified TIMEOUT. Outside: the pool kills the worker process (`Process.kill`,
  TerminateProcess on Windows) at a hard deadline of 2 × limit + 10 s, so a hang cannot stall
  a run.
- **Memory cap: sampled, not hard.** The parent samples each worker's RSS with psutil every
  50 ms and kills it above `--mem-cap-mb` (MEMOUT). A spike shorter than the sampling interval
  can overshoot; no OS-level limit (Windows job object / `RLIMIT_AS`) is set. Tested: a worker
  holding 400 MB under a 150 MB cap is killed.
- **One core per run** (single-threaded Python), but runs execute in parallel (`--jobs`), so
  timings include contention between workers; with more jobs than physical cores, contention
  grows. Default: physical cores.
- **k's minimality** is certified per instance (`oracle` or `exact-search`); `unknown`
  instances are excluded, never assumed optimal. `verify_minimality` is not passed to the timed
  calls (see Pipeline step 2); records carry `minimality` = `verified` (oracle) or `assumed`
  (exact-search certificate, which proves minimality by itself through Theorem E of
  MATHEMATICAL_INVARIANTS but is not the oracle check).
- **Selection bias.** Only instances whose ghw our Python search (or the 16-vertex oracle)
  can establish within the budget enter the table. These are small and mostly of low width; the
  paper's instances are much larger. The family-stratified sample over-represents small families
  relative to HyperBench.
- **Not reproduced:** the paper's decomposers (BalancedGo, log-k-decomp), htdLEO, the 30 min /
  1 GB / 1 core limits, the 1798-instance set with known ghw, absolute runtimes and speed-ups.

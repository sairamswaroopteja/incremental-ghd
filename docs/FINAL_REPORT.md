# FINAL REPORT (S15)

**Paper:** Gottlob, Lanzinger, Longo, Okulmus, *Incremental Updates of Generalized Hypertree Decompositions*, arXiv:2209.10375v1.
**Implementation:** `incremental-ghd/`, Python 3.12. The library is `src/ighd` (about 4,300 lines); with tests, benchmarks and examples the code totals about 12,500 lines.
**Authority:** where this report and the code disagree, the code and its tests win. Readings of the paper are recorded in `FAITHFULNESS_LEDGER.md`.

---

## 0. Verdict in one paragraph

Every **algorithmic** component of the paper's update framework is implemented and checked against independent references:
- the six modifications and s_δ (§3);
- the DelVar rule (§3.2);
- δ-mutable subtrees and Algorithm 2 (§4, Lemma 4.4);
- δ(H)\*, bag constraints and the gluing of Theorem 4.5;
- scene creation, Algorithms 3–4 (§5);
- GHDUpdate / DecompUpdate, Algorithm 5;
- a static GHD decomposer (Algorithm 1 with a connection set).

We still do **not** claim that "the paper is fully implemented":
1. Three of the paper's statements are **false or incomplete as written**, so the code implements a corrected version: A21, A26 and A16, described in §4. The corrections are required for correctness and are pinned by tests.
2. **Inputs to the scene-based update must already be in normal form.** No GHD normaliser was built. This is planned item R6. The THEOREM45 and RECOMPUTE strategies accept any valid GHD.
3. **The experiments (§6) are reproduced at the level of the protocol only.** The paper's decomposers (BalancedGo / log-k-decomp), the htdLEO baseline, its 30-minute / 1 GB limits and its absolute numbers are not reproduced.
4. **Some guarantees are checked at run time, not proved.** These are listed in §3.2.

---

## 1. Deliverables checklist (project brief §12)

| # | Deliverable | Status | Where |
|---|---|---|---|
| 1 | Complete modular implementation | **done** | `src/ighd/` with 11 subpackages; interfaces in `docs/ARCHITECTURE.md` |
| 2 | Working static GHD decomposer | **done** (EXACT and HEURISTIC) | `ighd.static.decomposer` |
| 3 | Working dynamic GHD update framework | **done** (PAPER, THEOREM45 and RECOMPUTE strategies) | `ighd.update.pipeline.ghd_update` |
| 4 | All six modifications | **done**, plus composition | `ighd.modifications` |
| 5 | Independent GHD validator | **done**. The validator's own code imports nothing algorithmic; see §6 for the limit of the import check | `ighd.ghd.validation` |
| 6 | Reproducible paper examples | **done** | `tests/paper_examples/`, `tests/dynamic_updates/test_update_paper_examples.py` |
| 7 | Unit and property tests | **done** | `tests/unit/`, hypothesis plus seeded corpora |
| 8 | Randomized and differential testing | **done**: 21,238-step chain run, Update vs oracle | `tests/dynamic_updates/`, `tests/randomized/`; `docs/TESTING_REPORT.md` |
| 9 | Mathematical correctness and invariants document | **done** | `docs/MATHEMATICAL_INVARIANTS.md` (Lemmas A–H) |
| 10 | Detailed implementation report | **done** | this file; `docs/PAPER_ANALYSIS.md`, `docs/IMPLEMENTATION_PLAN.md`, `PROGRESS.md` |
| 11 | Benchmark framework, Update vs recomputation | **done**: real HyperBench data, one reproducible run | `benchmarks/`, `benchmarks/README.md` |
| 12 | Clear instructions to run | **done** | `README.md`, `examples/quickstart.py` |

---

## 2. Feature matrix

### 2.1 Fully implemented (code, tests and a cross-check against an independent reference)

| Feature | Paper | Independent check |
|---|---|---|
| Hypergraph with named edges; induced subhypergraph; [U]-components on edges | §2.1, §2.3 | unit and property tests; paper examples |
| Six modifications with s_δ and `ModificationSequence` | Defs 3.2–3.4 | unit and property tests (injectivity of s_δ, inverse pairs) |
| GHD validator: edge coverage, connectedness, guard B_u ⊆ B(λ_u) | §2.2 | hand-built violations; the oracle's witnesses |
| Exact ghw oracle (subset DP over elimination orders with ρ) | — (test reference) | cross-checked against the decomposer on random hypergraphs |
| Static decomposer, EXACT mode | Alg 1 with conn (A13) | **Theorem E**: sound and complete, proved in MATHEMATICAL_INVARIANTS §2; differential against the oracle |
| Replay normal-form checker | §2.3, Def 5.1 | Lemma F; paper examples |
| δ-mutable conditions and Algorithm 2 (minimal δ-mutable subtree) | Def 4.1, Lemma 4.4 | equals the brute-force minimum on random cases (EDGEWISE reading, A2) |
| δ(H)\*, bag constraints and gluing | §4.1, Thm 4.5 | Lemma 4.2 checks; random repair tests; Lemma G |
| Scene creation down and up | Algs 3–4, Def 5.1 | Ex. 5.2 traced; random runs |
| DecompUpdate | Alg 5 | differential against the oracle; 21,238 chained steps |
| DelVar rule | §3.2, §6.1 | validity tests; NF reported (A29) |
| `ghd_update` with three strategies, input-minimality check, output validation | §3.2 SearchUpdateGHD | every answer agrees with the oracle in every random run |
| Benchmark harness on HyperBench: §6.1 generator, runner, Table 1 metrics, Fig. 7 plots | §6 | metrics recomputed by an independent script; answers checked against the oracle |

### 2.2 Partially implemented

| Feature | What is missing | Effect |
|---|---|---|
| Updating an arbitrary external GHD with scenes (PAPER strategy) | A **normaliser** (R6). Non-NF input raises `NotNormalFormError` (Def 5.1 precondition, A15) | Use THEOREM45 or RECOMPUTE for such inputs, or obtain the GHD from our decomposer, whose outputs are NF by Lemma F |
| Reproduction of §6 | BalancedGo / log-k-decomp, htdLEO, the paper's 1,798-instance set and its limits | Only the comparison protocol and the trends are reproduced, not the numbers |

### 2.3 Features that work only for restricted instances

| Component | Restriction | Why |
|---|---|---|
| Exact oracle `exact_ghw` | ≤ 16 vertices (`MAX_ORACLE_VERTICES`) | exponential subset DP |
| Brute-force mutable-subtree oracle | ≤ 12 GHD nodes | enumerates subtrees |
| `verify_minimality=True` | ≤ 16 vertices; larger inputs give `Minimality.ASSUMED` | depends on the oracle |
| EXACT decomposer in practice | small widths and small hypergraphs. 61 of 200 HyperBench instances with ≤ 30 vertices had no certified ghw within 20 s | exponential search, in Python |
| All exactness claims of the random tests | hypergraphs of ≤ 16 vertices, rank ≤ 3, chains ≤ 12–14 vertices; k = 3 never occurs in the chains | limited by the oracle and the generator (TESTING_REPORT §7) |

### 2.4 Heuristic components (sound, not complete)

| Component | Guarantee |
|---|---|
| `TopDownDecomposer(DecomposerMode.HEURISTIC)`, which only tries bags B = B(λ) ∩ (W ∪ conn) | Every output is a valid GHD (Lemma B). Failure gives `NOT_FOUND`, **never** `PROVEN_NO`. `ghw_by_search` in this mode returns an upper bound only |
| Any search cut off by a `Budget` (expansions or time) | Gives `NOT_FOUND` only (I10) |
| Scene hints passed to the decomposer (A19) | Only reorder candidates; they never change an EXACT verdict |
| The DelVar rule | Valid GHD of width ≤ k, but not necessarily minimal (A14) or in normal form (A29) |

### 2.5 Exact components

| Component | Exact in what sense |
|---|---|
| EXACT decomposer, unbudgeted | FOUND iff a GHD of width ≤ k exists (with connection set and coverage-only constraints): **Theorem E** |
| `ghd_update`, EXACT decomposer, unbudgeted, any strategy | Answers `UPDATED` iff ghw(δ(H)) ≤ k. `PROVEN_NO` is always the verdict of an exhaustive search over all of δ(H) at width k (MATHEMATICAL_INVARIANTS §6, "Authority of the verdict") |
| Oracle `exact_ghw`, `brute_mutable` | Exact within their size limits; these are the references |
| Algorithm 2 | Returns the unique minimum δ-mutable subtree under EDGEWISE (Lemma 4.4); under SET the minimum may not be unique (A2) |

---

## 3. Guarantees

### 3.1 Proven

| Statement | Proof |
|---|---|
| Lemma 4.2, Lemma 4.4, Theorem 4.5, Prop 5.3 | **paper**. Theorem 4.5 is used only within the scope fixed below |
| Theorem 4.5 holds for each of the six elementary modification classes (**Lemma G**). It is **false** for general δ (A26). Our fix is condition (iii) with a whole-tree fallback | **ours**, MATHEMATICAL_INVARIANTS §4; counterexample test |
| The EXACT search terminates (A), is sound (B), descends (C, C′, D), is complete (E), and its outputs are in normal form (F) | **ours**, MATHEMATICAL_INVARIANTS §2. **C′** repairs a gap in our own first proof |
| DecompUpdate with `restrict_reused_bags=True` returns only valid GHDs and terminates (**Lemma H**) | **ours**, MATHEMATICAL_INVARIANTS §6 |
| `PROVEN_NO` from `ghd_update` means ghw(δ(H)) > k (EXACT, unbudgeted) | Theorem E, plus the A18 top-level fallback (§6) |
| No polynomial-time update is claimed | paper Theorem 3.6: SearchUpdateGHD is not in P for AddVar, AddConstr, DelConstr, AddEq and DelEq unless P = NP |

### 3.2 Guaranteed by a run-time check, not by a proof

| Statement | Mechanism |
|---|---|
| Every `UPDATED` output is a GHD of δ(H) with width ≤ k | The independent validator runs on every output. An invalid result raises `InvalidGHDError` and is never returned. This matters for the **literal default** `restrict_reused_bags=False` (A28), where validity is not proved |
| Every edge containing a new vertex lies in V\* (I8); the outer-tree interface (I5); Algorithm 2's working tree stays a connected subtree (I7) | assertions in `constraints.target`, `constraints.constraints` and `mutable.minimal` |
| Input precondition: width k, and normal form for scenes | `validate` and `check_normal_form` on entry; the oracle when ≤ 16 vertices |

### 3.3 Empirical observations (corpus-dependent rates, not guarantees)

| Observation | Measurement |
|---|---|
| All strategies agree with the exact oracle | 1,950 S12 differential cases; 21,238 S13 chain steps (369 PROVEN_NO, all oracle-confirmed); widened-distribution tests; **2,137 HyperBench pairs checked against the oracle** (S14/S15) |
| Without the A21 interface check, literal Alg 5 returns **invalid GHDs**, including wrong YES answers | 37 / 3,000 on the S12 corpus; 17 / 3,000 on the S13 corpus, 11 of them wrong YES |
| Without restriction (literal A28), no invalid output occurred with the default checks on | all random runs; not proved |
| A18 fallback frequency | 159 / 3,000 (S12), 101 / 3,000 (S13) |
| Algorithm 5's outputs are in normal form | every random case (not proved). The DelVar rule's outputs are not NF in 25–31% of cases (A29) |
| Reuse of old nodes (PAPER strategy, non-DelVar) | about 43% |
| Theorem 4.5's constraints never caused a NO that a full search would turn into a YES | 0 / 7,200 random cases |
| Scene creation scales roughly as N³ on paths (Prop 5.3) | a timing sanity check, not a measurement of the bound |
| **HyperBench, Update vs Classic** (§5 below) | Update is faster on harder instances, while Classic wins on the tiniest ones |

---

## 4. Problems found in the paper

All are pinned by tests (`-m paper_discrepancy`, plus the tests named in the ledger).

| ID | Location | Finding | Consequence | Resolution |
|---|---|---|---|---|
| **A26** | §4, Thm 4.5 proof | Theorem 4.5 is **false for arbitrary δ**: an edge changed only by *existing* vertices can escape δ(H)\*. Reachable by composing AddVar and AddEq | wrong (non-GHD) output | Lemma G proves it for the six classes; other δ check condition (iii) and otherwise fall back to the whole tree |
| **A21** | Alg 5 | Reuse of a scene node does not check the **parent interface** conn ⊆ bag | **wrong YES answers** under the paper's own readings | interface check, on by default |
| **A16** | Ex. 5.2 vs Alg 3 L3 | The example maps C₂ ↦ u₂, but the pseudocode rejects u₂, and the example's σ yields an invalid guard | example inconsistent with the algorithm | follow the pseudocode |
| A17 | Alg 4 L16 vs prose | The key of an upward scene is ambiguous; the literal key can break connectedness | invalid output under the literal reading | COVERED_EDGES (the line-14 comment) |
| A22 | Thm 3.6 proof idea | ghw values 2 and 3 are swapped relative to Appendix A.2 | documentation only | the appendix is correct |
| A25 | Def 5.1 vs Alg 3 L9 | in/out kind of a scene at an ancestor of T\* | reuse differs | pseudocode (conservative) |
| A27 | Def 5.1 vs Alg 3 | σ can map one edge set to two nodes, so it is not a function | ambiguity | the deeper entry wins, logged |
| A28 | Alg 5 L6 | A reused bag may contain vertices outside V(H′) ∪ conn | validity unproved under the literal reading | literal default, validated at run time; a sound restriction option (Lemma H) |
| A29 | §3.2/§6.1 vs Def 5.1 | The DelVar rule's output is not always in NF, but the next update requires NF | chaining breaks | `delvar_fast_path=False`; NF reported in every result |
| A18, A19, A20, A23 | Alg 3 and Alg 5 | rejection propagation, use of σ by the decomposer, δ missing on `u.Bag`, non-injective matching | under-specified | completions listed in the ledger |

Our own error: the first completeness proof of the static search missed arbitrary top-level connection sets. **Lemma C′** fixes it, with a test.

---

## 5. Benchmarks (S14): what was and was not reproduced

The run is `benchmarks/results/small-seed0/`.
- **Command:** `python -m benchmarks.run --preset small --seed 0`.
- **Setup:** HyperBench instances with ≤ 30 vertices, a family-stratified sample of 200; the §6.1 generator with 5 modifications per class (DelVar excluded, as in the paper); 10 s per run; the same EXACT decomposer for Update (PAPER) and Classic (RECOMPUTE).
- **Input width k:** certified for each instance, by the oracle (88) or by an exact search (50). 62 instances were excluded: 61 had no certificate, and 1 was killed for memory.

| | pairs | Positive % | Better % | GM Update | GM Classic | GM speed-up | timeouts exclusive U/C | total U/C |
|---|---|---|---|---|---|---|---|---|
| all | 3,355 | 86.4 | 41.4 | 4.70 ms | 7.37 ms | 1.57 | 1/10 | 102/111 |
| Classic > 15 ms | 1,074 | 69.8 | 67.9 | 30.7 ms | 210 ms | 6.84 | 1/10 | 102/111 |

- **Correctness inside the benchmark:** Update and Classic disagreed 0 times. No output failed validation and no run errored. Both systems matched the exact oracle on all 2,137 pairs small enough to check.
- **Trend:** in line with the paper's Fig. 7, Update's advantage grows with ghw and |E|. On millisecond-scale instances, the overhead of Algorithm 2 and the scenes dominates, and Classic is faster.
- **Not comparable with the paper:**
  - a different decomposer (Python exact search, not BalancedGo / log-k-decomp) and a different machine;
  - 10 s instead of 30 min; a memory cap enforced only by sampling;
  - parallel workers, whose timings include contention;
  - a corpus of small, low-width instances (ghw 1–3).
- The HEURISTIC mode is supported by the harness but was not part of this run.

---

## 6. Testing summary

Details are in `docs/TESTING_REPORT.md`.
- **Default suite** `python -m pytest`: **691 passed**, 15 `slow` tests deselected.
- **Slow suite** `-m slow`: 15 passed, including the 10⁴-step criterion, which ran 21,238 steps.
- **Independent references:** the exact oracle, brute-force mutable subtrees, and the validator.
- **Function-level execution scan (S15):** every one of the 193 functions in `src/ighd` runs during the default suite. Before S15, four never ran:
  - the frozen public wrapper `update.decomp_update.decomp_update`;
  - the `__repr__` methods of `GHD` and `SceneMapping`, together with the `name` helper nested inside `GHD.__repr__`.

  `tests/dynamic_updates/test_decomp_update_api.py` now covers them. A function that runs is not necessarily tested thoroughly; this scan only rules out functions that are never exercised.
- **Traceability gaps closed after S15:**
  - the A8 T\* pin;
  - `Minimality.REFUTED`;
  - direct checks of I6 and I7 (I7 also as a run-time assertion);
  - the A29 `paper_discrepancy` pin.

  Still without a dedicated test: Lemma A (termination; every search in the suite terminates), and A10 and A22, which are documentation only.
- **The validator independence test checks direct imports only.** Importing `ighd.ghd` also loads `ighd.static.separation` through the normal-form checker, although the validator's own code uses nothing from it.

---

## 7. Known limitations

1. **Exponential components:** the decomposer, the oracle and therefore all exactness checks. This is unavoidable, since the problem is NP-hard (Thm 3.6). Practical scale is small hypergraphs and small widths.
2. **No normaliser:** the PAPER strategy rejects non-NF inputs.
3. **The literal default (A28) relies on run-time validation for YES answers.** The proven variant is `Semantics(restrict_reused_bags=True)`.
4. **Generator biases:** the random tests use rank ≤ 3, few edges and k ≤ 2 in the chains. About 21% of chain steps start from a non-minimal GHD, which lies outside the paper's precondition; their answers are still exact for the k used.
5. **Benchmarks:** limited scale, and timings measured under parallel load. The memory cap is sampled, not enforced by the OS.
6. **Not built:** a GHD normaliser, the BalancedGo / log-k-decomp decomposers, htdLEO, and hypothesis profiles `ci`/`deep`. Each test file uses fixed `derandomize=True` settings instead.
7. **No version control:** git was never initialised. That is still your call.

---

## 8. How to run

See `README.md`. In short:

```bash
python -m pytest
python -m pytest -m slow
python examples/quickstart.py
python -m benchmarks.run --preset smoke
python -m benchmarks.run --preset small --seed 0
```

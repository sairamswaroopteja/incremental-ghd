# PROGRESS

| Phase / stage | Status |
|---|---|
| Phase 1: paper analysis and implementation plan | done, approved |
| S0: skeleton, frozen interfaces, paper fixtures | done, interfaces signed off |
| S1 Hypergraph · S3 GHD tree (W1) | done, reviewed |
| S2 Modifications · S4 Validator · S5 Oracle · S6 Components (W2) | done, reviewed |
| S7 Decomposer · S8 NF checker · S9 Algorithm 2 (W3) | done, reviewed (Lemma C′) |
| S10 δ(H)*, constraints, gluing · S11 scenes (W4) | done, reviewed (A26, A27) |
| **S12: GHDUpdate (Algorithm 5), strategies, DelVar fast path** (main agent) | **done** (A28, A29, A21 evidence) |
| **S13: testing harness and TESTING_REPORT** (agent T, reviewed) | **done**: done criterion met (21,238 chain steps) |
| **S14: benchmark framework** (agent F, reviewed) | **done**: HyperBench, §6.1 generator, runner, metrics, Fig. 7 plots; small run complete |
| **S15: final reports** (main agent) | **done**: `docs/FINAL_REPORT.md` |

**All stages S0–S15 are complete.**

## Tests
- `python -m pytest`: **691 passed, 0 failed**, 15 `slow` deselected.
- `-m slow`: **15 passed**.
- `-m paper_discrepancy`: 16 tests.
- Details, traceability and limitations: `docs/TESTING_REPORT.md`.

## Gap closure after S15 (main agent)
- **A8:** `test_a8_merge_target_inside_or_outside_u_changes_t_star`. Path a-b-c-d with merge {a,b}: w = b gives T* = {n1}, a fresh w gives T* = T. Both were derived by hand and equal the brute-force minimum.
- **A29:** `test_a29_delvar_rule_output_is_not_normal_form_and_breaks_chaining` (paper_discrepancy). The smallest non-NF case from a seeded search; the next scene update raises `NotNormalFormError`.
- **`Minimality.REFUTED`:** reported under every strategy, and the answers stay exact for the input width.
- **I7:**
  - a runtime assertion in `mutable/minimal.py` (the only library change), shown to be live by `test_i7_assertion_fires`;
  - every intermediate working tree of Algorithm 2 is checked against the brute-force oracle: 300 cases with 153 intermediate trees, slow 3,000 cases with 1,514.
- **I6:** every reused node's cover equals δ(λ_u), and its bag equals δ(B_u) (or is contained in it under restriction), for PAPER literal, PAPER restricted and THEOREM45. 200 cases by default; slow 2,000 cases with 2,386 / 2,386 / 1,076 reused nodes. No violation was found.
- **Coverage floors:** two thresholds in the new tests were first set above what the seeds produce. They were lowered to the observed counts; they are floors on how many cases are exercised, not correctness checks.

## S15 summary (main agent)
- **`docs/FINAL_REPORT.md`**: the verdict (not "fully implemented", with the reasons), the brief §12 deliverables checklist, and the feature matrix (full / partial / restricted / heuristic / exact). Guarantees are split into proven, run-time-checked and empirical. It also covers the paper issues, the benchmark summary and the known limitations.
- **Function-level execution scan of `src/ighd`** (profiling plugin, default suite):
  - 4 of 193 functions never ran: the frozen public wrapper `decomp_update`, the `__repr__` of `GHD` and `SceneMapping`, and a helper nested inside `GHD.__repr__`;
  - `tests/dynamic_updates/test_decomp_update_api.py` now covers them (the public wrapper equals the pipeline's entry; a failure returns no GHD);
  - after the fix, all 193 run.
- **Doc claims corrected to match the code** (an audit; no code change):
  - I6 and I7 were checked only indirectly, and the planned debug assertion for I7 did not exist (both closed later, see below);
  - I9 is a reuse check, not an assertion;
  - the A8 pin was planned but never written (MATHEMATICAL_INVARIANTS, PAPER_ANALYSIS, ledger);
  - the scope of the validator independence check (ARCHITECTURE);
  - the `Semantics` row now lists A28.
- **New:** `examples/quickstart.py` (tested by `tests/test_examples.py`) and a rewritten `README.md` with run instructions.

## S13 summary (agent T; main-agent review: diff read, no check relaxed)
- **Slow `test_random_update_chains_10k`**: seeds 101–120, **21,238 steps, 0 failures, 369 PROVEN_NO**, every one confirmed by the oracle; 2,193 composite steps, 22 of them A26 fallbacks.
- **`run_chains` gained three checks**:
  - the starting width equals the oracle's ghw;
  - PROVEN_NO asserts ghw > k;
  - after a PROVEN_NO, the restart width equals ghw.
- **`tests/randomized/test_generator_gaps.py`**:
  - Lemma G checked directly against brute force;
  - a non-vacuity check on the A26 counterexample;
  - modification types the shared generator never produces (A8 AddEq into a fresh vertex, DelEq with both parts new, AddConstr on only fresh vertices), checked against the oracle under five variants, including Lemma H's `restrict_reused_bags`.
- **Rates re-measured on another corpus** (seed 3000): 17 of 3,000 invalid outputs without A21, 11 of them wrong YES; A18 fallback 101 of 3,000; DelVar outputs not in NF 25%; reuse 43–44%. The earlier figures (37, 159, 31%) came from a different corpus. Both are corpus-dependent rates, not guarantees.
- **Traceability gaps**, kept open for S15:
  - A8's "w ∈ U vs w ∉ U changes T*" pin is missing;
  - `Minimality.REFUTED` is never asserted;
  - I6 (a reused cover is not enlarged) is covered only indirectly;
  - I7's debug assertion does not exist;
  - A29's test is not marked `paper_discrepancy`;
  - the validator's AST independence check is narrower than claimed: importing `ighd.ghd` loads `ighd.static` through `normal_form`, although the validator uses nothing from it.
- **Generator biases**: k = 3 never occurs in the chains, and 21% of chain steps start from a non-minimal GHD (answers still exact for the k used).

## S14 summary (agent F; main-agent review)
- **HyperBench** was downloaded with your approval: a 2.26 MB zip over plain HTTP (HTTPS was refused). All **3,000 `.hg` files parse**.
- **Harness**: top-level `benchmarks/` with a CLI (`python -m benchmarks.run --preset smoke|small`) and `benchmarks/README.md`, which carries the honesty notes. Runs:
  - in spawned workers, with a hard kill at 2× the limit + 10 s and a sampled RSS watchdog (1 GB; not an OS-level limit);
  - any run that overshoots its time limit counts as TIMEOUT.
- **The input k is certified per instance**, by the oracle (≤16 vertices) or by an exact search that also proves k−1 impossible. Instances without a certificate are excluded and counted.
- **Run `small-seed0`** (seed 0, ≤30 vertices, family-stratified 200, 5 modifications per class, 10 s per run, 4 workers, 23 min):
  - instance funnel: 200 selected; 88 certified by the oracle, 50 by exact search, 61 skipped (ghw not established in 20 s), 1 killed for memory;
  - 3,355 modifications, 95 not generatable with reasons;
  - 6,710 runs.

  | (EXACT decomposer) | Positive % | Better % | GM Update | GM Classic | GM speed-up | timeouts excl. U/C | timeouts total U/C |
  |---|---|---|---|---|---|---|---|
  | all pairs | 86.4 | 41.4 | 4.70 ms | 7.37 ms | 1.57 | 1/10 | 102/111 |
  | Classic > 15 ms (the paper's filter) | 69.8 | 67.9 | 30.7 ms | 210 ms | 6.84 | 1/10 | 102/111 |

  - By class under the filter, the speed-up is 25.7 for AddEq, 28.4 for DelConstr, 6.1 for AddVar, 3.3 for AddConstr and 2.1 for DelEq.
  - Fig. 7 (`plots/fig7_exact.png`): Update's advantage grows with ghw and |E|. On the smallest instances Classic is faster; Update's overhead dominates there.
- **Independent review** (my own script, not the harness code):
  - **0 Update/Classic disagreements**, 0 validation failures, 0 errors;
  - Better % and the geometric means recomputed and matching;
  - **all answers of both systems on the 2,137 pairs with δ(H) ≤ 16 vertices equal the exact oracle**, with δ(H) re-derived from the stored specs.
- **Not reproduced**: BalancedGo / log-k-decomp, htdLEO, 30 min / 1 GB limits, the paper's 1,798 instances, and absolute numbers. Our decomposer is a Python exact search, so the corpus is limited to small widths (ghw 1–3). The workers run in parallel, so timings include contention. The HEURISTIC mode is implemented but was not in the small run.

| Area | Tests |
|---|---|
| S0–S11 (see earlier rows) | 615 (+9 slow) |
| S12 paper examples, end to end | 37 |
| S12 differential vs oracle | 1 (+1 slow) |
| S12 randomized chains | 1 (+1 slow) |

## S12 summary (main agent)
- **Implemented:**
  - `update/decomp_update.py`: Algorithm 5's DecompUpdate. It covers the stateful in-scene lookup, δ-mapped bag and cover (A20), the guard and interface checks (A16, A21), the progress check, the A18 fallback, and decomposer calls with scene hints (A19, `SceneHintDecomposer`, never consuming).
  - `update/delvar.py`: the paper's DelVar rule.
  - `update/pipeline.py`: `ghd_update`, with three strategies (PAPER, THEOREM45, RECOMPUTE), the A26 condition-(iii) check, the minimality check against the oracle (A14), validation of every output, an NF note, and the authoritative PROVEN_NO rule (I10).
- **Paper examples end to end:**
  - Example 4.3/5.2 under PAPER: u1 (in-scene) and u3 (out-scene) are reused with identical bags and covers; u2 is rejected at Algorithm 3 line 3. u4 is not reused because this decomposer's candidate order prefers the larger bag {e,i,j,k,l} for {w3,w6}. That is a legitimate decomposer choice (the paper leaves `D` open).
  - All 7 guide/paper cases × 3 strategies give the correct answer, with minimality VERIFIED for every input.
  - AddConstr {c,i} on Fig. 3 reuses all four nodes with zero decomposer calls: w7 already lies in t1's bag, and the scenes find this by themselves.
- **Differential (Level 5):**
  - 150 default plus 1,800 slow cases × 4 strategy variants. Every answer equals the oracle's: UPDATED iff ghw(δ(H)) ≤ k. 88 cases are PROVEN_NO, with no NOT_FOUND, all strategies agree, and every output validates.
  - The PAPER strategy reuses about 43% of old nodes (non-DelVar).
- **Randomized chains (Level 6):** about 3,150 chained steps (plus 236 default) with PAPER and DelVar through Algorithms 2–5. Every step agrees with the oracle, validates and is in NF. 49–179 steps per run started from a non-minimal input; composite sequences hit the A26 fallback twice and were handled correctly.

## New findings in S12 (details: PAPER_ANALYSIS §4, ledger)
1. **A21 is required by the paper's own algorithm.** Under the default readings, literal Algorithm 5 without the interface check returned **invalid GHDs in 37 of 3,000 random updates**, including a **wrong YES**: on a 3-edge path plus AddConstr {d,e,f} it returned a width-1 "GHD" with vertex e disconnected, while ghw is 2. Pinned by `test_a21_interface_check_is_required_by_the_paper_algorithm`.
2. **A29: the DelVar rule's output is not always in normal form** (31% of random DelVar updates), which Def 5.1 requires of the next update. Algorithm 5's outputs were NF in every case. Option `delvar_fast_path=False`; every result reports NF.
3. **A28:** Algorithm 5 reuses old bags as is. Under the literal default no invalid output was observed; the restriction option is provably valid (Lemma H, MATHEMATICAL_INVARIANTS §6).
4. A18 fallback: 159 of 3,000 random updates; pinned with a deterministic case.

## Paper issues found so far
A16 (Ex. 5.2 vs Alg 3), A17 (scene key), A21 (missing interface check: produces wrong answers), A22 (swapped ghw values), A25 (in/out kind), **A26 (Theorem 4.5 false for arbitrary δ)**, A27 (σ not a function), A28, A29. Our own proof gap: Lemma C′.

## Known bugs
None.

## Still awaiting your answer
1. Optional: the BalancedGoUpdate source (not downloaded). HyperBench: approved and done.

## Next recommended action
The project is complete as planned. Optional follow-ups, none of which blocks the results:
1. **A GHD normaliser (R6)**, so that the PAPER strategy accepts any valid GHD.
2. **A larger benchmark run**, or the HEURISTIC mode, or an external decomposer, for scale.

Version control: a git repository was initialised on branch `main`, with all stages in the first commit.

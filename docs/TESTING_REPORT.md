# TESTING_REPORT (S13)

Scope: the test suite under `tests/` for the `ighd` implementation of Gottlob, Lanzinger, Longo,
Okulmus, *Incremental Updates of Generalized Hypertree Decompositions* (arXiv:2209.10375).
`benchmarks/` and `tests/benchmarks/` (S14, agent F) are **not** covered or counted here.

Every number in this report was either **measured** by agent T on 2026-11-16 (marked *[measured]*)
or **copied** from `PROGRESS.md` / `FAITHFULNESS_LEDGER.md` / `MATHEMATICAL_INVARIANTS.md`
(marked *[copied]*). Timings come from one Windows 11 laptop, Python 3.12, while another agent was
running benchmarks on the same machine. Treat them as rough, not as performance data.

---

## 1. Summary

| Item | Result |
|---|---|
| Default suite `python -m pytest` | **657 passed, 0 failed, 13 deselected** (`slow`), 136 s in the final run (80 s in an earlier run the same day; PROGRESS.md recorded about 42 s on an idle machine) *[measured]* |
| Slow suite `python -m pytest -m slow` | **13 passed, 0 failed**, 324 s in the final run (262 s for the 12 slow tests before `test_widened_distribution_large` was added) *[measured]* |
| `paper_discrepancy` tests | 15 (all in the default suite) |
| **S13 done criterion** (plan §C): ≥ 10⁴ seeded chain steps, zero validator failures, every PROVEN_NO agrees with the oracle | **met**: 21,238 chain steps (seeds 101–120), 0 failures, 369 PROVEN_NO, every one with ghw(δ(H)) > k by the exact oracle *[measured]* |
| Known failing tests / open bugs | none |
| After S14 (main agent, re-run) | **681 passed, 13 deselected** (79 s): the 657 above plus 24 benchmark-harness tests in `tests/benchmarks/` (generator shapes and determinism, metrics on hand-made records, end-to-end runner, TIMEOUT never reported as PROVEN_NO, pool hard kill and memory kill) *[measured]* |
| After S15 gap closure (main agent) | **691 passed, 15 deselected**; `-m slow` **15 passed**; 16 `paper_discrepancy` tests. New: A8 T* pin, A29 pin (pd), `Minimality.REFUTED`, I7 replay against the brute-force oracle (300 cases / 153 intermediate trees; slow 3,000 / 1,514) plus a live runtime assertion, I6 reused-cover check (200 cases; slow 2,000: 2,386 PAPER and 1,076 THEOREM45 reused nodes), and the `decomp_update` wrapper and repr tests *[measured]* |
| S14 benchmark answers vs oracle (main agent, independent script) | run `small-seed0`: 3,355 Update/Classic pairs, **0 disagreements**, 0 harness validation failures; the 2,137 pairs whose δ(H) has ≤ 16 vertices were re-derived from the stored modification spec with `ighd.modifications.ops` and **all answers of both systems equal the exact oracle** *[measured]* |

### Tests added in S13
- `tests/dynamic_updates/test_update_sequences.py`:
  - **`test_random_update_chains_10k`** (`slow`): 20 seeds × 100 chains × up to 20 modifications, with the same per-step checks as the existing chain tests (§3.6).
  - `run_chains` gained three **stricter** checks:
    - the chain's starting width equals the oracle's ghw, so the input is minimal;
    - on PROVEN_NO, `truth > k` is asserted explicitly;
    - on restart after PROVEN_NO, the decomposer's new k equals the oracle's ghw.
  - It also gained counters (kind, k, skipped draws). No existing check was removed or relaxed.
  - The RNG stream is unchanged, so the old seeds give the same cases: seeds 1–4 still produce 3,149 steps, as in PROGRESS.md.
- `tests/randomized/test_generator_gaps.py` (new, 3 default tests plus 1 slow):
  - **Lemma G**, tested directly: every brute-force δ-mutable subtree satisfies condition (iii).
  - A non-vacuity check of the condition-(iii) predicate on the A26 counterexample.
  - Level 5 on a **widened modification distribution** (A8 AddEq into a fresh vertex, DelEq with both parts new, all-fresh AddConstr), with five strategy variants, including **Lemma H** (`restrict_reused_bags=True`).

---

## 2. Independent references

| Reference | Module | Scope / limits | Independence |
|---|---|---|---|
| Exact ghw oracle `exact_ghw` | `ighd.oracle.ghw_dp`, `edge_cover` | subset DP over elimination orderings. Raises `OracleTooLargeError` above **16 vertices** (`MAX_ORACLE_VERTICES`) | different method from the decomposer (DP over orderings vs. top-down separator search) |
| Brute-force mutable subtrees `all_mutable_subtrees` | `ighd.oracle.brute_mutable` | all 2^|T| node subsets, connectedness by BFS, Def 4.1 (i) and (ii) literally. Limit **12 nodes** (`MAX_BRUTE_NODES`) | independent of Algorithm 2 |
| Validator `validate` | `ighd.ghd.validation` | GHD conditions (1)–(3), width, typed violations | written by a separate agent. It imports only `common.types`, `ghd.tree`, `hypergraph.core` |
| Naive references inside tests | e.g. permutation brute force (`test_oracle_ghw`, `test_decomposer_differential`), BFS component definition (`test_separation_properties`), naive GHD check (`test_validation`), GYO acyclicity | tiny instances (≤ 5–7 vertices) | written in the test files |

**The independence rule is enforced by an AST test.** `tests/test_s0_smoke.py::test_independence_rule_imports` parses `ghd.validation`, `oracle.edge_cover`, `oracle.ghw_dp` and `oracle.brute_mutable`. It fails if any of them imports from `ighd.static`, `update`, `scenes`, `constraints` or `mutable`.

What the AST test does **not** cover:
- It checks *direct* imports only. Importing `ighd.ghd.validation` executes the package `ighd/ghd/__init__.py`. That file imports `normal_form`, which imports `ighd.static.separation`, so `ighd.static` gets loaded *[measured: `sys.modules` after the import]*. The validator's code uses no name from those modules. This is a packaging side effect, not shared logic, but the AST test would not catch a future *use* that goes through a re-export.
- The NF checker (`check_normal_form`) is **not** independent of the decomposer: both use `static.separation.components`. `components` itself is checked against a naive BFS definition (`test_separation_properties.py::test_matches_naive_reference`).
- The update pipeline validates its own outputs and raises `InvalidGHDError` on any violation, so an invalid GHD can never be returned silently. The tests validate every output **again**, independently.

---

## 3. Results by testing level (IMPLEMENTATION_PLAN §F)

Test counts below are collected test items (parametrisations included). Default = not `slow`.

### 3.1 Level 1: unit tests

| Area | Files | Default tests |
|---|---|---|
| Hypergraph, induced subhypergraphs, comparison, HyperBench parser | `unit/test_hypergraph_core.py` (31), `unit/test_hypergraph_compare.py` (19), `unit/test_hypergraph_io.py` (24) | 74 |
| Modifications (Defs 3.2–3.4, Ex. 3.5, A5–A9, sequences) | `unit/test_modifications.py` (50) | 50 |
| GHD tree (split, glue, reroot, spec round-trip, deep paths) | `unit/test_tree.py` (42) | 42 |
| Validator (one mutant per violation kind, A4) | `unit/test_validation.py` (20) | 20 |
| Exact oracle (paper ghw values, size guard, edge cover) | `unit/test_oracle_ghw.py` (105, incl. 80 seeded cross-checks) | 105 |
| Brute-force mutable subtrees (A2, Lemma 4.4) | `unit/test_oracle_mutable.py` (77) | 77 |
| [U]-components (A3) | `unit/test_separation.py` (17) | 17 |
| Decomposer (k=0, conn, coverage-only, budget, scene hints A19, Lemma C′) | `unit/test_decomposer.py` (33) | 33 |
| NF checker | `unit/test_normal_form.py` (16) | 16 |
| Algorithm 2 / Def 4.1 checker | `unit/test_mutable.py` (20) | 20 |
| δ(H)*, bag constraints (I5, I8, A11, A12), gluing | `unit/test_constraints.py` (17), `unit/test_gluing.py` (8) | 25 |
| Scenes (Algs 3–4, A16, A17, A20, A23, A25, A27), SceneMapping | `unit/test_scenes.py` (15), `unit/test_scene_mapping.py` (7) | 22 |
| S0 smoke: interfaces, semantics defaults = ledger, independence AST rule, fixture transcription | `test_s0_smoke.py` (33) | 33 |

**Reference:** hand-computed values from the paper and the study guide (`tests/fixtures/expected.py` records each value's provenance). **Result:** all pass.

### 3.2 Level 2: property tests (hypothesis and seeded corpora)

| Property | File | Examples | Reference |
|---|---|---|---|
| Incidence round trip; $H[U][W]=H[W]$; parser round trip; edgewise ⇒ set equality | `test_hypergraph_core.py`, `test_hypergraph_io.py`, `test_hypergraph_compare.py` | 200 each, `derandomize=True` | definitions |
| Invariants of every modification class; inverse pairs; composition = stepwise application | `test_modifications_properties.py` | 100 each | definitions |
| Traversals, components, reroot, split + glue = original, spec round trip | `test_tree_properties.py` | 200 each | definitions |
| Validator agrees with a naive check on random (mostly invalid) trees; oracle witnesses validate | `test_validation.py` | 300 / 100 | naive check in test |
| Edge cover = naive; ghw = permutation brute force; ghw 1 ⇔ α-acyclic (GYO); bounds | `test_oracle_ghw.py` | 100 / 40 / 60 / 60 | permutation brute force, GYO |
| Components = BFS definition; partition; A3 literal reading adds exactly the inside singletons | `test_separation_properties.py` | 150 each | naive BFS |
| Lemma 4.4: the EDGEWISE family is the upward closure of a unique minimum | `test_oracle_mutable.py` | 60 seeds | brute force |
| Scene creation properties (Def 5.1 coverage of scene keys, kinds, single use) | `test_scenes.py::test_random_properties` | 1,500 seeds (≥ 1,300 cases asserted) | definitions; asserts every Alg 3/4 branch is reached |

All hypothesis tests use fixed per-file `settings(derandomize=True, …)`. The plan's named hypothesis profiles (`ci`, `deep`) were **not** implemented. **Result:** all pass.

### 3.3 Level 3: paper examples

| What | File | Tests |
|---|---|---|
| Ex. 2.3 / Fig. 3 / Fig. 4: components, connection sets, assembled tree; forcing the root separator via a scene hint reproduces Fig. 3 | `paper_examples/test_ex23.py` | 5 |
| Ex. 4.3: T* = {u1,u2}, the **exact** Algorithm 2 step log, SET gives the same | `paper_examples/test_ex43_alg2.py` | 5 |
| Ex. 5.2: σ under the defaults; L3 fires at u2; the paper's printed σ is unsafe (A16); alternative up keys (A17) | `paper_examples/test_ex52_scenes.py` | 5 |
| Every expected T* (paper + guide §8, 7 cases) equals the oracle's unique minimum; ghw before and after | `paper_examples/test_expected_t_star_oracle.py` | 21 |
| Theorem 4.5 route on Ex. 4.3 ($C_3=\{a,h\}$, $C_4=\{k\}$, repaired GHD = guide §6.8), glue refusal, A26 counterexample | `paper_examples/test_thm45_repair.py` | 13 |
| End-to-end SearchUpdateGHD: 7 cases × 3 strategies with minimality VERIFIED; Ex. 4.3/5.2 trace; A12, A16, A17, A18, A21, A26, A28, A29 pins; NOT_FOUND for HEURISTIC and budget; input checks | `dynamic_updates/test_update_paper_examples.py` | 37 |

**Reference:** the paper's stated values, the study guide's traces, and the oracle (each expected T* and each ghw is re-derived by the oracle, never trusted blindly). **Result:** all pass. Where the paper's text conflicts with its pseudocode, both readings are pinned (§5).

### 3.4 Level 4: dynamic (six classes, minimal input, validate, width ≤ k)

Covered by the parametrised `test_every_case_every_strategy` (paper/guide cases, all six classes, PAPER / THEOREM45 / RECOMPUTE, `verify_minimality=True`). The random levels below cover it at scale. Every case is UPDATED with a valid output of width ≤ k, except AddVar(h) on the join tree of $H_P$, which is PROVEN_NO with ghw 1 → 2 (oracle).

### 3.5 Level 5: differential (Update vs Theorem45 vs Recompute vs oracle)

| Test | Corpus (seeded) | Checks | Size | Result |
|---|---|---|---|---|
| `unit/test_decomposer_differential.py::test_ghw_matches_oracle` (+ slow ×3) | family A: ≤ 7 vertices, ≤ 6 edges; family B: dense graphs on 6–7 vertices; plus $K_6$ | EXACT ghw = oracle; k = ghw−1 gives PROVEN_NO; HEURISTIC sound; FOUND outputs valid and NF | default 391 instances (seed 20240917); slow 3 × 1,151 | pass. Slow ghw distribution: A {1: 2,327, 2: 673}, B {2: 80, 3: 373} *[measured]* |
| `…::test_coverage_only_matches_brute_force`, `test_conn_tasks_match_brute_force` (+ slow) | tiny (≤ 5 vertices) | constrained EXACT FOUND ⇔ permutation brute force ≤ k, k ∈ {1,2,3} | 200 + 200 (slow 2,000 + 2,000) | pass |
| `unit/test_mutable_differential.py` (+ slow) | ≤ 8 vertices, ≤ 7 edges, oracle witness GHDs | Algorithm 2 T* = unique brute-force minimum (EDGEWISE); order independence; SET statistics recorded | default 6 × 60 + 2,400; slow 12,000 | pass. Slow: T* empty 107, whole tree 6,864 of 12,000 *[measured]* |
| `integration/test_alg2_on_decomposer_ghds.py` (+ slow) | decomposer (compact NF) GHDs | same, on the inputs the update actually receives | 300; slow 3 × 1,500 | pass. Slow: proper T* 1,662 / 4,500, never empty *[measured]* |
| `integration/test_thm45_random.py` (+ slow) | ≤ 7 vertices, ≤ 6 edges, six classes round-robin | ghw(δH) > k ⇒ not FOUND; FOUND ⇒ valid, width ≤ k, outer trees kept verbatim (Lemma 4.2, I4) | 1,200; slow 4 × 1,500 | pass. Slow: 5,647 found, 353 genuine NO, **0 constraint-induced NO** *[measured]* |
| `dynamic_updates/test_update_differential.py` (+ slow) | shared generator, 20% dense rank-2 | 4 variants (PAPER fast on/off, THEOREM45, RECOMPUTE): UPDATED ⇔ oracle ≤ k, never NOT_FOUND, all agree, outputs valid, PAPER outputs NF | 150; slow 3 × 600 | pass. Slow: 88 of 1,800 cases have ghw rising (PROVEN_NO) *[measured; matches PROGRESS]* |
| `randomized/test_generator_gaps.py::test_updates_on_widened_distribution_agree_with_oracle` (+ slow) **new** | widened distribution (A8 fresh target, DelEq both parts new, all-fresh AddConstr) | 5 variants incl. `restrict_reused_bags=True` (Lemma H): same checks | 400 (seed 2718); slow 3 × 1,000 | pass. Default: 13 rises / 400; slow: 88 rises / 3,000 *[measured]* |

### 3.6 Level 6: randomized chains (`dynamic_updates/test_update_sequences.py`)

**Method.**
- A chain starts from a random hypergraph (4–7 vertices, 3–6 edges, rank ≤ 3) and a minimal NF GHD from the EXACT decomposer. Minimality is asserted against the oracle.
- It then applies up to *steps* random modifications: elementary, or with probability 0.15 a composed two-step `ModificationSequence`.
- Every step uses the PAPER strategy with `delvar_fast_path=False` (L-A29).
- A chain stops once H has more than 12 vertices, or δ(H) has more than 14 (oracle limits).

**Per-step checks** (unchanged in S13, three made stricter):
1. never NOT_FOUND;
2. UPDATED ⇔ ghw(δ(H)) ≤ k (oracle);
3. on UPDATED: the output validates, has width ≤ k, and is in NF;
4. on PROVEN_NO: ghw(δ(H)) > k (oracle). The chain restarts from a fresh minimal GHD, whose width is asserted to equal the oracle's ghw.

The next step's k is the output's width, so it may be **non-minimal** (minimality ASSUMED).

| Test | Seeds × chains × max steps | Steps | UPDATED | PROVEN_NO | composite | A26 fallback | non-minimal next input | time |
|---|---|---|---|---|---|---|---|---|
| `test_random_update_chains` (default) | 4242 × 40 × 8 | 236 | 227 | 9 | 36 | 0 | 49 | 0.4 s |
| `test_random_update_chains_large` (slow) | 1–4 × 100 × 12 | 3,149 | 3,070 | 79 | 376 | 2 | 567 | 5.7–19.7 s |
| **`test_random_update_chains_10k`** (slow, new) | **101–120 × 100 × 20** | **21,238** | **20,869** | **369** | 2,193 | 22 | 4,506 | 34–81 s (37 s when run alone) |

All figures above are *[measured]*. The 3,149 and 236 match PROGRESS.md. Mix of the 21,238 steps:
- **By class:** DelConstr 4,365, DelVar 4,125, AddEq 4,092, AddVar 2,257, DelEq 2,203, AddConstr 2,003, composite 2,193.
- **By input k:** k = 1 for 14,291 steps, k = 2 for 6,947. **k = 3 never occurred.**
- **Rejected draws:** 7,985 drawn modifications were rejected by `apply` and skipped (they are not counted as steps), see §7.

**Result: zero failures, so the S13 criterion is met.**

---

## 4. Traceability: invariant / lemma / theorem / ambiguity → tests

Found by grepping the test files for each ID and then reading the tests. Hits on Algorithm line tags such as `A3:L3` and `A4:L16` were discarded, since those are Algorithm 3/4 lines, not ambiguities A3/A4. **Gap** means no test pins the item; *indirect* means it is only implied by other assertions.

### 4.1 Invariants (MATHEMATICAL_INVARIANTS §1)

| ID | Pinned by | Status |
|---|---|---|
| I1 output is a GHD of δ(H) | the pipeline validates every output (raises otherwise); every update test re-validates (`test_update_paper_examples`, `test_update_differential`, `test_update_sequences`, `test_generator_gaps`) | tested |
| I2 input width k; = ghw when verified | `test_every_case_every_strategy` (`Minimality.VERIFIED`); chain starts and restarts asserted equal to the oracle's ghw (S13); `test_input_checks` (k below width rejected) | tested (on random inputs only at chain starts and restarts) |
| I3 scene input in NF | `test_input_checks` (`NotNormalFormError`), `unit/test_scenes.py::test_non_normal_form_input_is_rejected`; Lemma F tests | tested |
| I4 outer trees are GHDs of δ(H)[T′] (Lemma 4.2) | `integration/test_thm45_random.py` (`assert_lemma42`), `paper_examples/test_thm45_repair.py` | tested |
| I5 one tree edge per outer tree; $C_i$ | `unit/test_constraints.py::test_i5_one_constraint_per_outer_tree` + runtime assertion | tested |
| I6 covers ≤ k, never enlarged | width ≤ k asserted everywhere; **S15**: `randomized/test_invariants_i6_i7.py::test_i6_reused_covers_are_delta_images` (+ slow): every reused node's cover equals δ(λ_u) and its bag equals δ(B_u) (⊆ under restriction), under PAPER literal, PAPER restricted and THEOREM45 | tested (S15) |
| I7 Algorithm 2's working tree is δ-mutable at every step | **S15**: runtime assertion in `mutable/minimal.py` (live: `test_i7_assertion_fires`); `randomized/test_invariants_i6_i7.py::test_i7_every_intermediate_working_tree_is_mutable` (+ slow) replays the step log against the brute-force oracle; earlier: `check_log_invariants`, the upward-closure test | tested (S15) |
| I8 edges with a new vertex lie in V* | `unit/test_constraints.py::test_i8_fires_on_non_mutable_t_star` + runtime assertion | tested |
| I9 scene node roots c only if conn ⊆ δ(B_u), δ(B_u) ⊆ B(δ(λ_u)) | `test_a21_interface_check_is_required_by_the_paper_algorithm`, `test_a17_a21_literal_up_key_needs_interface_check`, `test_a16_paper_printed_sigma_yields_invalid_ghd` | tested via the checks' consequences; no runtime assertion named I9 |
| I10 PROVEN_NO only from an unbudgeted EXACT search of all δ(H) | `test_heuristic_never_proves_no_and_budget_never_proves_no`; `unit/test_decomposer.py::test_heuristic_never_proven_no`, `test_tiny_budget_gives_not_found`; every random PROVEN_NO is oracle-confirmed | tested (budget/heuristic only on single cases) |

### 4.2 Lemmas and theorems

| Result | Kind | Pinned by |
|---|---|---|
| Lemma A (termination) | proven (MI §2.2) | *indirect*: every search terminates in the tests; no dedicated test |
| Lemma B (soundness), Lemma F (NF outputs) | proven (MI §2.3, §2.7) | `test_decomposer_differential.py` (every FOUND validated and NF), HEURISTIC soundness, `test_scenes.py::_random_instance` asserts NF |
| Lemma C / D / Theorem E (EXACT complete) | proven (MI §2.4–2.6) | `test_ghw_matches_oracle` (+ slow); constrained and conn corpora vs brute force |
| Lemma C′ (top-level conn) | proven, gap found in review | `test_conn_root_extension_is_needed` (disabling the extension makes the conn corpus fail) |
| Lemma G (Thm 4.5 holds for the six classes) | proven (MI §4) | **new**: `test_lemma_g_every_mutable_subtree_satisfies_condition_iii` (300 cases default, 3,000 slow, every brute-force mutable subtree); non-vacuity: `test_condition_iii_check_is_not_vacuous`. Before S13: *indirect* only |
| Lemma H (`restrict_reused_bags` sound) | proven (MI §6) | `test_a28_restricting_reused_bags_masks_a16` (1 case); **new**: the `paper_restrict` variant in `test_generator_gaps.py` (400 default, 3,000 slow) |
| Lemma 4.2 | paper | `assert_lemma42` in `test_thm45_random.py`, `test_thm45_repair.py`; `test_example_43_theorem45_strategy` |
| Lemma 4.4 (unique minimum, Alg 2 finds it) | paper | `test_mutable_differential.py`, `test_alg2_on_decomposer_ghds.py`, `test_expected_t_star_oracle.py`, `test_oracle_mutable.py` |
| Theorem 4.5 (constructive) | paper (scope corrected, A26) | `test_thm45_random.py`, `test_thm45_repair.py`, `test_gluing.py` |
| Prop 5.3 (scene creation $O(N^3)$) | paper | `test_prop53_runtime_on_paths` (slow): a timing *sanity* check on paths (factor ≤ 16 from N=100 to 200), not a proof |
| Theorem 3.6 (hardness) | paper | not testable; reflected in NOT_FOUND vs PROVEN_NO and no polynomial-time claim |

### 4.3 Ambiguities (PAPER_ANALYSIS §4)

| ID | Pinned by | Status |
|---|---|---|
| A1 | `test_hypergraph_core.py::test_induced_drops_empty` | tested |
| A2 | `test_hypergraph_compare.py::test_a2_counterexample_edgewise_vs_set` (pd); `test_oracle_mutable.py::test_a2_*`, `test_random_search_for_a2_divergence`; `test_mutable_differential.py` (SET stats); `test_ex43_set_semantics_same_result` | tested |
| A3 | `test_separation.py::test_a3_literal_reading_makes_inside_edges_singletons` (pd); `test_separation_properties.py::test_literal_reading_adds_exactly_the_inside_singletons` | tested |
| A4 | `test_validation.py::test_a4_vertex_coverage_is_not_enough` | tested |
| A5 | `test_modifications.py::test_invalid_parameters_raise` (`addvar_existing_vertex`, `addvar_empty_edges`) | tested (not tagged "A5" in the test) |
| A6, A7 | `test_modifications.py::test_delvar_empties_singleton_edge`, `test_delconstr_w6_removes_j_and_l` | tested |
| A8 | `test_modifications.py::test_addeq_into_fresh_vertex`; `test_mutable_differential.py` and `test_thm45_random.py` generators; **new**: `test_generator_gaps.py` (fresh-target AddEq through the full update) | tested. **S15**: `unit/test_mutable.py::test_a8_merge_target_inside_or_outside_u_changes_t_star` (w = b gives T* = {n1}, w = z gives T* = T; both equal the brute-force minimum) |
| A9 | `test_hypergraph_core.py::test_duplicate_vertex_sets_stay_distinct`, `test_modifications.py::test_addeq_two_edges_become_equal`, `test_delvar_can_create_duplicate_edges` | tested |
| A10 | none | **gap** (by design: the plan states it cannot matter) |
| A11 | `test_constraints.py` (δ(H)* target tests, I8) | tested |
| A12 | `test_mutable.py::test_fresh_edge_gives_empty_t_star`, `test_oracle_mutable.py`, `test_constraints.py`, `test_gluing.py`, `test_update_paper_examples.py::test_empty_t_star_fresh_edge` | tested |
| A13 | `paper_examples/test_ex23.py`; conn tests in `test_decomposer.py` | tested (not tagged "A13") |
| A14 | `test_delvar_fast_path_and_non_optimality`; `Minimality.VERIFIED` in `test_every_case_every_strategy` | tested; **S15**: `test_minimality_refuted_is_reported_and_answers_stay_exact` (REFUTED under every strategy; answers stay exact for k = input width) |
| A15 | `test_input_checks`, `test_scenes.py::test_non_normal_form_input_is_rejected` | tested |
| A16 | `test_ex52_without_line3_reproduces_stated_sigma_which_is_unsafe` (pd), `test_a16_paper_printed_sigma_yields_invalid_ghd` (pd) | tested |
| A17 | `test_ex52_alternative_up_scene_keys` (pd, 2 params), `test_a17_a21_literal_up_key_needs_interface_check` (pd) | tested |
| A18 | `test_a18_fallback_after_child_failure` | tested |
| A19 | `test_decomposer.py::test_scene_hints_never_change_exact_verdict` | tested |
| A20 | `test_ex52_scenes.py`, `test_scenes.py`; exercised by the A16 end-to-end test | tested |
| A21 | `test_a21_interface_check_is_required_by_the_paper_algorithm` (pd), `test_a17_a21_…` (pd) | tested |
| A22 | none | **gap** (documentation only: a typo in a proof sketch) |
| A23 | `test_scenes.py::test_literal_first_match_maps_two_children_to_one_component` (pd), `test_strict_matching_goes_upward_instead` | tested |
| A24 | S14 `tests/benchmarks/test_metrics.py` (exclusive and total timeouts on hand-made records) | tested (S14) |
| A25 | `test_scenes.py::test_ancestor_of_t_star_gets_in_scene` (pd) | tested |
| A26 | `test_thm45_fails_for_a_general_modification` (pd), `test_a26_composed_modification_falls_back` (pd, 2 params); random chains (22 fallbacks in the 10k run) | tested |
| A27 | `test_scenes.py::test_child_scene_overwrites_parent_scene_for_same_key` (pd), `test_scene_mapping.py::test_overwrite_is_recorded` | tested |
| A28 | `test_a28_restricting_reused_bags_masks_a16` (pd) | tested |
| A29 | **S15** (pd): `test_a29_delvar_rule_output_is_not_normal_form_and_breaks_chaining` (concrete non-NF output; the next scene update is refused); `test_delvar_without_fast_path_is_normal_form`; NF asserted for every Algorithm 5 output in the differential and chain tests | tested |
| C′ (own proof) | `test_conn_root_extension_is_needed` | tested |

(pd) = marked `paper_discrepancy`.

**Gaps, in summary:**
- A10 and A22 (documentation only).
- Lemma A directly.
- *(Closed in S15: the A8 T* pin, `Minimality.REFUTED`, I6 and I7 directly, the A29 marker; A24 is covered by S14's metrics tests.)*
- No hypothesis profiles.

---

## 5. Paper-discrepancy tests (`-m paper_discrepancy`, 16 items after S15)

| Test | Pins |
|---|---|
| `unit/test_hypergraph_compare.py::test_a2_counterexample_edgewise_vs_set` | **A2**: the $\{y,z\}$ vs $\{y\},\{z\}$ counterexample. EDGEWISE and SET differ, and Lemma 4.4's union step needs EDGEWISE |
| `unit/test_separation.py::test_a3_literal_reading_makes_inside_edges_singletons` | **A3**: the literal definition makes inside edges singleton components; Examples 2.3/5.2 do not |
| `paper_examples/test_ex52_scenes.py::test_ex52_without_line3_reproduces_stated_sigma_which_is_unsafe` | **A16**: skipping Alg 3 L3 reproduces Ex. 5.2's printed σ, and u2's δ-guard misses c |
| `paper_examples/test_ex52_scenes.py::test_ex52_alternative_up_scene_keys[LITERAL_H_PRIME, INTERSECTING_EDGES]` | **A17**: both alternative keys map {w3,w6} ↦ u4, whose bag misses the connection vertex e |
| `paper_examples/test_thm45_repair.py::test_thm45_fails_for_a_general_modification` | **A26**: Theorem 4.5 fails for a non-elementary δ (edge changed by an existing vertex) |
| `unit/test_scenes.py::test_ancestor_of_t_star_gets_in_scene` | **A25**: Def 5.1 vs Alg 3 L9. An ancestor of T* outside T* gets IN |
| `unit/test_scenes.py::test_literal_first_match_maps_two_children_to_one_component` | **A23**: the L16 first match is not injective on a real case |
| `unit/test_scenes.py::test_child_scene_overwrites_parent_scene_for_same_key` | **A27**: σ is not a function; the deeper entry wins and is logged |
| `dynamic_updates/test_update_paper_examples.py::test_a26_composed_modification_falls_back[PAPER, THEOREM45]` | **A26**: condition (iii) is detected and T* := whole tree, so the update is correct |
| `…::test_a16_paper_printed_sigma_yields_invalid_ghd` | **A16** end to end: the validator reports `UnguardedVertices` |
| `…::test_a28_restricting_reused_bags_masks_a16` | **A28**: restricting reused bags happens to repair the printed σ (recorded, not relied upon) |
| `…::test_a17_a21_literal_up_key_needs_interface_check` | **A17 + A21**: the literal key with no interface check gives `DisconnectedVertex` |
| `…::test_a21_interface_check_is_required_by_the_paper_algorithm` | **A21**: a wrong YES (width-1 "GHD", ghw 2) from literal Algorithm 5 under the default readings |

**Added in S15:** `dynamic_updates/test_update_paper_examples.py::test_a29_delvar_rule_output_is_not_normal_form_and_breaks_chaining`, which pins **A29**: the paper's DelVar rule turns {e0: ae, e1: ab} with root {a,b} and child {a,e} into a valid but non-NF GHD, and the next scene-based update is refused. A22 (a proof-sketch typo) has no test, by design.

---

## 6. Exact vs proven vs empirical

### 6.1 Exact (oracle-confirmed, on the stated corpora only)
- EXACT decomposer ghw = oracle ghw on every tested instance: 391 default and 3,453 slow instances, ≤ 7 vertices, ghw 1–3.
- Algorithm 2's T* = the unique brute-force minimum (EDGEWISE): 2,760 default + 12,000 slow (oracle witnesses), and 300 + 4,500 (decomposer GHDs), all ≤ 12 nodes.
- SearchUpdateGHD answer = oracle (UPDATED ⇔ ghw(δH) ≤ k; PROVEN_NO ⇔ ghw(δH) > k) on:
  - Level 5: 150 + 1,800 cases × 4 variants;
  - widened distribution: 400 + 3,000 cases × 5 variants;
  - chains: 236 + 3,149 + 21,238 steps.
- Every output validated, and never NOT_FOUND with the EXACT unbudgeted decomposer.
- Every PROVEN_NO in every random run was oracle-confirmed (9 + 79 + 369 in the chains).

### 6.2 Proven (pointers into `docs/MATHEMATICAL_INVARIANTS.md`)
- Lemmas A–F and Theorem E (§2): the EXACT search is sound, complete and terminating, and its outputs are in NF. This is why `PROVEN_NO` is a proof (I10).
- Lemma C′ (§2.4′): completeness for arbitrary top-level `conn`.
- Lemma G (§4): Theorem 4.5 holds for the six elementary classes; general δ needs condition (iii).
- Lemma H (§6): DecompUpdate is valid with `restrict_reused_bags=True`.
- Paper results used as stated: Lemma 4.2, Lemma 4.4, Theorem 4.5 (scope corrected by A26).

**Not proven:**
- validity of the literal default (`restrict_reused_bags=False`): it is *checked* on every output;
- NF of Algorithm 5's outputs;
- Prop 5.3's bound for our implementation.

### 6.3 Empirical observations (rates; corpus-dependent, not guarantees)

| Observation | Value | Source |
|---|---|---|
| A21: literal Alg 5 without the interface check returns an invalid GHD | 37 / 3,000 updates, incl. a wrong YES | *[copied]* PROGRESS.md |
| same, re-measured on a different corpus (seed 3000, Level-5 generator, PAPER, fast path on) | **17 / 3,000** invalid (pipeline raises `InvalidGHDError`); 11 of those 17 had ghw(δH) > k, i.e. would have been wrong YES answers | *[measured]* |
| A18 fallback frequency | 159 / 3,000 *[copied]*; **101 / 3,000** on the corpus above *[measured]* | |
| A29: DelVar rule output not in NF | 31% *[copied]*; **130 / 519 = 25.0%** *[measured]* | |
| Algorithm 5 outputs not in NF | 0 in every run: 2,345 / 2,345 (corpus above); all chain and differential steps (asserted) | *[measured]* |
| PAPER reuse of old nodes (non-DelVar) | ≈ 43% *[copied]*; **1,519 / 3,538 = 42.9%** (Level-5 slow run); **2,600 / 5,917 = 43.9%** (corpus above) *[measured]* | |
| A26 fallback in chains (composite steps only) | 2 in 3,149 steps *[copied, re-measured]*; **22 in 21,238** (2,193 composite) *[measured]* | |
| Chain steps that start from a non-minimal GHD (precondition of SearchUpdateGHD not met) | 4,506 / 21,238 = 21.2% *[measured]*. Answers are still exact w.r.t. the k used | |
| Theorem 4.5 route: constraint-induced NO (constraints too strong although ghw ≤ k) | **0** in 1,200 + 6,000 random cases *[measured]* | |
| A27 (σ overwrite) | 16 in 1,469 random scene-creation runs (`test_scenes.py::test_random_properties`) | *[copied]* MI §5, *[re-measured, identical]* |
| A2: SET vs EDGEWISE | slow S9 run: SET Alg 2 differs from EDGEWISE in 2,301 / 12,000; SET minimum not unique in 138 *[measured]*; 13 / 60 *[copied]* ledger | |
| Prop 5.3 sanity (scene_create on paths, best of 3) | N = 25, 50, 100, 200: 0.0025, 0.0104, 0.0548, 0.5404 s in one run, 0.009, 0.030, 0.137, 1.290 s in another (ratio 9.9 and 9.4 from N = 100 to 200, above the factor 8 of N³; the test allows 16). Machine under load | *[measured]* |

---

## 7. Limitations

1. **Exactness claims are for small hypergraphs only.**
   - The ghw oracle refuses more than 16 vertices, and the brute-force mutable-subtree oracle refuses more than 12 nodes.
   - The random corpora use 4–7 starting vertices; chains stop above 12 vertices, with δ(H) ≤ 14.
   - Nothing in this report says anything about correctness on HyperBench-size instances. There, only validity (validator) and the honesty of `NOT_FOUND` vs `PROVEN_NO` can be checked, and that is S14's job.
2. **Generator biases** (`ighd.testing.generators`):
   - **Rank and width:** rank ≤ 3 (dense family: rank 2), ≤ 6 initial edges (dense: ≤ 10). In the chains k ∈ {1, 2} only, with **k = 3 never reached**. ghw 3 occurs only in the decomposer differential's dense family B and $K_6$.
   - **Fixed fresh names:** z, y, v2 and `wnew` are fixed names, so once present a second AddVar("z") or AddConstr("wnew") is rejected. In the 10k run, `apply` rejected 7,985 draws, against 21,238 accepted steps. A hypergraph never carries two generator-made fresh vertices with the same name.
   - **AddEq / DelEq / AddConstr variants:** the shared generator always merges AddEq into an existing merged vertex (w ∈ U), always keeps the DelEq vertex, and uses at most one fresh vertex in AddConstr. The new widened test covers the other variants, but only at Level 5, not in chains.
   - **Composites:** only two-step sequences.
   - **Small GHDs, so T* is often the whole tree.** T* was the whole tree in 2,838 / 4,500 cases (Algorithm 2 integration, slow) and 3,858 / 6,000 (Theorem 4.5 random, slow). The Lemma G test sees on average about 1.9 mutable subtrees per case (574 / 300 default). The Algorithm 2 integration test asserts ≥ 30% proper T*.
3. **Checked only on single, deterministic or budgeted cases:**
   - the HEURISTIC decomposer and budgets in the update pipeline: `NOT_FOUND`, never `PROVEN_NO`, on one case each;
   - `verify_minimality=True`: the 7 paper cases;
   - non-default semantics switches (`up_scene_key`, `strict_child_matching=False`, `scene_guard_check=False`, `scene_interface_check=False`, SET comparison): pinned on crafted cases, never run through randomized updates (`restrict_reused_bags=True` is now randomized);
   - the A21/A18/A29 rates: measured by ad-hoc scripts, not by an asserted test.
4. **Not tested at all:**
   - a GHD normaliser (it does not exist, R6: non-NF inputs are rejected);
   - updates on instances above the oracle limits;
   - time or memory limits other than `Budget(max_expansions)`;
   - A10 and A22 (see §4.3).
5. **Prop 5.3** is a timing sanity check on one family (paths) under machine noise, not evidence of a complexity bound. No polynomial-time claim is made for any update class (Theorem 3.6).
6. **Shared code** between the judge and the judged: `check_normal_form` and the decomposer share `components`. The validator and oracles share only data types (`Hypergraph`, `GHD`) with the code they judge.

---

## 8. How to reproduce

From the project root (Windows: the `PYTHONPATH` separator is `;`):

```bash
python -m pytest                                    # default: 657 passed, 13 deselected
python -m pytest -m slow -s                         # slow: 13 passed, prints all statistics
python -m pytest -m paper_discrepancy               # the 15 discrepancy pins
python -m pytest --collect-only -q                  # per-file counts (default)
python -m pytest --collect-only -q -m slow          # per-file counts (slow)
python -m pytest --durations=15                     # timings

# S13 criterion only (prints per-seed and total counters, as in §3.6)
python -m pytest "tests/dynamic_updates/test_update_sequences.py::test_random_update_chains_10k" -m slow -s

# Lemma G / widened distribution / Lemma H
python -m pytest tests/randomized -m "" -s

# validator import side effect (§2)
PYTHONPATH="src" python -c "import sys, ighd.ghd.validation; print(sorted(m for m in sys.modules if m.startswith('ighd.static')))"
```

The empirical rates marked *[measured]* in §6.3 (A21 without the interface check, A18, A29, reuse on seed 3000) came from an ad-hoc script that is not part of the suite. Its method:
- 3,000 cases from `tests/dynamic_updates/test_update_differential.py::_family` with seed 3000;
- `ghd_update` with defaults, then again with `Semantics(scene_interface_check=False)`;
- count `L-A18` notes, `InvalidGHDError` exceptions, NF of DelVar fast-path outputs, and `len(trace.reused_nodes) / len(base)` for non-DelVar UPDATED results.

All of this uses public API only. The copied figures (37/3000, 159/3000, 31%) came from S12 runs on a different corpus.

# ARCHITECTURE — frozen interfaces (S0)

This document summarises the public interface fixed in S0. The source of truth is the stubs in
`src/ighd/`: every public function exists with its final signature and raises
`NotImplementedError("... stage Sx ...")` until its stage lands. Changing an interface after
sign-off requires a main-agent decision recorded here.

## Core vocabulary (`ighd.common`)

| Name | Meaning |
|---|---|
| `Vertex = str`, `EdgeName = str`, `NodeId = int` | hypergraph vertex, named hyperedge, decomposition node. Never mixed |
| `VertexSet`, `EdgeSet` | `frozenset` of the above |
| `SearchStatus` | `FOUND` / `PROVEN_NO` (exhaustive EXACT search only) / `NOT_FOUND` |
| `UpdateStatus` | `UPDATED` / `PROVEN_NO` / `NOT_FOUND` |
| `Minimality` | input GHD width `VERIFIED` = ghw, `ASSUMED`, or `REFUTED` |
| `DecomposerMode` | `EXACT` (complete) / `HEURISTIC` (sound, incomplete) |
| `Semantics`, `PAPER_DEFAULT` | ambiguity switches A2, A3, A16, A17, A21, A23, A28 (see FAITHFULNESS_LEDGER) |
| `Budget` | expansion/time limits; exhaustion raises `BudgetExhausted` → only ever `NOT_FOUND` |

## Modules and key signatures

```
hypergraph.core        Hypergraph(edges: Mapping[EdgeName, Iterable[Vertex]])
                         .edges .edge_names .vertices .edge(n) .incident(v) .covered_vertices(names)
                         .neighbors(v) .adjacent_to(vs) .degree(v) .rank() .induced(U) -> {name: e∩U ≠ ∅}
                         .subhypergraph(names) .with_edges(...) .without_edges(...) .has_duplicate_edges()
hypergraph.compare     induced_diff(old, new, U, s_delta, mode) -> InducedDiff ; induced_equal(...) -> bool
hypergraph.io_hyperbench  parse_hyperbench(text) -> Hypergraph ; to_hyperbench(h) -> str

modifications.base     ModificationResult(kind, old, new, s_delta, new_edges, new_vertices,
                         removed_vertices, description) .removed_edges ; Protocol Modification.apply(h)
modifications.ops      AddVar(vertex, edges) DelVar(vertex) AddConstr(name, vertices) DelConstr(name)
                         AddEq(merge, into) DelEq(vertex, parts: {new_vertex: edges})
modifications.sequence compose(results) ; ModificationSequence(steps)

ghd.tree               Node(id, bag, cover, label) ; GHD() / GHD.from_spec(spec) / .to_spec()
                         add_node set_labels copy root node node_ids by_label parent children tree_neighbors
                         preorder postorder subtree_nodes ancestors is_connected leaves_of bag_union width
                         reroot components_without extract attach(at, other, other_node) -> id map
ghd.validation         validate(h, ghd) -> ValidationReport(violations, width, edge_cover_map, warnings).ok
                         violations: UncoveredEdge DisconnectedVertex UnguardedVertices UnknownCoverEdge UnknownBagVertex
ghd.normal_form        check_normal_form(h, ghd, semantics) -> NFReport(ok, handled, failed_node, reason)

oracle.edge_cover      edge_cover_number(h, B) -> int | None ; minimum_edge_cover(h, B)
oracle.ghw_dp          exact_ghw(h) -> (ghw, witness GHD)          [guard: MAX_ORACLE_VERTICES = 16]
oracle.brute_mutable   all_mutable_subtrees(change, ghd, semantics) [guard: MAX_BRUTE_NODES = 12]

static.separation      components(h, edges, U, semantics) -> list[EdgeSet] ; inside_edges ; connection
static.decomposer      DecompositionTask(hypergraph, k, edges, conn, coverage_only, guard_pool)
                         Protocol Decomposer.decompose(task, *, scenes, budget) -> DecompResult(status, ghd, root, mode, stats)
                         TopDownDecomposer(mode) ; ghw_by_search(h, mode, budget)

mutable.conditions     mutable_conditions(change, ghd, t_star, semantics) -> MutabilityCheck(...).mutable
mutable.minimal        minimal_mutable_subtree(change, ghd, semantics) -> MutableResult(t_star, steps: Alg2Step...)

constraints.target     redecomposition_target(change, ghd, t_star) -> RedecompositionTarget(vertices, edges, full_edges)
constraints.constraints bag_constraints(ghd, t_star) -> [BagConstraint(outer_node, inner_neighbor, outer_tree, vertices)]
constraints.gluing     glue(d_star, old, constraints) -> GHD

scenes.mapping         SceneKind{IN,OUT} ; SceneEntry(node, kind, origin, consumed)
                         SceneMapping.add/peek/lookup(stateful)/overwritten/items
scenes.scene_down      scene_create(change, ghd, t_star, semantics) -> (SceneMapping, [SceneEvent])
scenes.scene_up        scene_create_up(change, ghd, node, h_prime, t_star, semantics) -> (SceneMapping, EdgeSet)

update.result          Strategy{PAPER, THEOREM45, RECOMPUTE} ; UpdateTrace(...) ; UpdateResult(status, ghd, k, width, minimality, strategy, trace)
update.pipeline        ghd_update(h, ghd, modification, *, k, strategy, decomposer, semantics, verify_minimality, budget)
update.decomp_update   decomp_update(change, old_ghd, edges, conn, k, sigma, decomposer, budget) -> DecompResult
```

## Rules enforced by tests

- `ighd.ghd.validation` and `ighd.oracle.*` import nothing from `static`, `update`, `scenes`, `constraints` or `mutable`. Checked by AST in `test_independence_rule_imports`. Scope (S13/S15 audit): the check covers *direct* imports of those modules. Importing `ighd.ghd.validation` runs the package `ighd/ghd/__init__.py`, which loads `normal_form`, which uses `static.separation.components`. The validator's own code calls nothing from it. The normal-form checker (not the validator) shares `components` with the decomposer.
- No package re-exports a name equal to one of its submodules (`test_no_submodule_is_shadowed_by_a_reexport`).
- `PAPER_DEFAULT` equals the readings in FAITHFULNESS_LEDGER (`test_semantics_defaults_match_ledger`).

## Shared test data

`tests/fixtures/paper.py` holds the paper's hypergraphs ($H_P$, $H_{P'}$, $H_{P_2}$, $H_{P_3}$), Example 2.1 (scopes, words, solution), the GHDs of Fig. 3 and Fig. 6(a), and two GHDs constructed in the study guide. Every item carries a provenance tag.

`tests/fixtures/expected.py` holds the expected intermediate results for S1–S11, also with provenance. It includes both the pseudocode reading and the paper's stated reading of Example 5.2.

## Interface extensions after sign-off

All of these are backward compatible: new optional parameters with defaults, or new names. No frozen signature changed.

| Stage | Extension | Why |
|---|---|---|
| S7 | `TopDownDecomposer._scene_candidates` hook (private) | A19 scene hints |
| S11 | `SceneMapping.merge`, `__contains__`; `SceneEvent` lives in `scenes.mapping` and is re-exported from `scene_down` | "add σ′ to σ"; avoids an import cycle |
| S12 | `Semantics.restrict_reused_bags` (default False) | L-A28 |
| S12 | `ghd_update(..., delvar_fast_path=True)` | L-A29 |
| S12 | `decomp_update(..., *, semantics=PAPER_DEFAULT)`; `update.decomp_update.Fragment`, `fragment_from_ghd`, `fragment_to_ghd`, `SceneHintDecomposer`, `run_decomp_update`, `delta_bag`, `delta_cover` | DecompUpdate builds nested fragments and assembles the GHD once |
| S12 | `update.delvar.delvar_update`; `update.pipeline.changed_or_new_edges_outside`, `ELEMENTARY` | DelVar fast path; L-A26 condition (iii) |
| S12 | package `ighd.testing` (`random_hypergraph`, `random_modification`, `KINDS`) | shared seeded generators (M13) |
| S13 | `tests/randomized/` (Lemma G, Lemma H, widened modification distribution); slow 10⁴-step chain test | S13 done criterion; traceability gaps |
| S14 | top-level package `benchmarks/` (outside `src/ighd`, imports only the public API): `loader`, `generator` (§6.1, seeded), `pool` (spawned workers, hard kill, RSS watchdog), `worker`, `runner`, `metrics`, `report`, `plots`, CLI `python -m benchmarks.run` | M14; no library interface changed |
| S15 | `examples/quickstart.py`; tests for the public `decomp_update` wrapper | deliverable 12; function-level execution scan |

## The update pipeline (S12) at a glance

```
ghd_update(H, G, δ)
  ├─ validate(H, G) ; k := width(G) ; [exact_ghw(H) → Minimality]
  ├─ change := δ.apply(H)                         (δ(H), s_δ, V_new)
  ├─ RECOMPUTE → decomposer(δ(H), k)               ── the paper's "Classic"
  ├─ DelVar & fast path → delete v from every bag  (paper §3.2)
  ├─ T* := Algorithm 2 ; non-elementary δ: condition (iii) else T* := T   (L-A26)
  ├─ THEOREM45 → δ(H)*, constraints, decomposer(coverage_only), glue ; else recompute
  └─ PAPER → σ := Algorithms 3–4 ; DecompUpdate (Alg 5: reuse | A18 fallback | decomposer with hints)
  └─ validate(δ(H), out) ; width ≤ k ; NF noted ; UPDATED | PROVEN_NO | NOT_FOUND
```

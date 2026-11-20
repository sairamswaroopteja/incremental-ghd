# CODE WALKTHROUGH: how the paper's algorithms are laid out in code and the order in which they run

This document is about the **code**: which file implements which algorithm, which function calls which, and the order things execute in for one modification.
- The mathematics is in `PAPER_ANALYSIS.md` and `MATHEMATICAL_INVARIANTS.md`.
- Every reading of the paper is recorded in `FAITHFULNESS_LEDGER.md`.
- Line numbers refer to the current sources.

---

## 1. The layers

The code is layered. Each layer only uses the layers below it.

```
 front ends      online/web.py + static/app.js (browser)   online/cli.py (terminal)   benchmarks/   tests/
                        \                                    |                            |
 session         online/session.py  OnlineSession.apply  (adds exact ghw tracking)        |
                        \____________________________________|____________________________/
 pipeline        update/pipeline.py  ghd_update  ── the paper's SearchUpdateGHD (§3.2)
                    |            |                 |                     |
 algorithms      mutable/      scenes/           update/decomp_update  constraints/        static/
                 (Alg 2)       (Alg 3, Alg 4)    (Alg 5)               (Thm 4.5)           (Alg 1: decomposer)
                    \            |                 |                     |                   /
 data            hypergraph/ (Hypergraph, components)   modifications/ (six ops, s_delta)   ghd/ (GHD tree)
 judges          ghd/validation.py (validator)   ghd/normal_form.py   oracle/ (exact ghw, brute force)
 shared          common/ (types, Semantics switches, Budget, errors)
```

The **judges** (the validator and the oracles) import nothing from the algorithm packages. A test enforces this. The pipeline calls the validator on every output, so an invalid GHD can never be returned.

---

## 2. The paper's algorithms, and where each lives

| Paper | Function (entry point) | File | What it computes |
|---|---|---|---|
| Algorithm 1: top-down decomposition (with a connection set, A13) | `TopDownDecomposer.decompose` → `_Search.solve` / `_try` / `build` | `src/ighd/static/decomposer.py` (333, 249, 278, 292) | a GHD of width ≤ k of the edge set C whose root bag contains conn, or a proof that none exists |
| [U]-components, connection set (§2.3) | `components`, `connection` | `src/ighd/static/separation.py` (26, 97) | used by Algorithms 1, 3, 4 and 5 and by the normal-form checker |
| Def 4.1: δ-mutable subtree | `mutable_conditions` | `src/ighd/mutable/conditions.py` (36) | conditions (i) and (ii) for a candidate T* |
| **Algorithm 2**: minimal δ-mutable subtree | `minimal_mutable_subtree` | `src/ighd/mutable/minimal.py` (41) | T*, with a log of every tested leaf |
| §4.1: δ(H)\* and bag constraints | `redecomposition_target`, `bag_constraints` | `src/ighd/constraints/target.py` (34), `constraints.py` (36) | the part to re-decompose, and what its bags must contain |
| Theorem 4.5: gluing | `glue` | `src/ighd/constraints/gluing.py` (18) | D\* with the untouched outer trees re-attached |
| **Algorithm 3**: SceneCreationDown | `scene_create` → `_down` | `src/ighd/scenes/scene_down.py` (127, 69) | σ: which old node may be reused for which edge set |
| **Algorithm 4**: SceneCreationUp | `_up` (`scene_create_up` standalone) | `src/ighd/scenes/scene_up.py` (119, 159) | out-scenes found bottom-up when going down fails |
| σ itself | `SceneMapping` (`add`, `merge`, `peek`, `lookup`) | `src/ighd/scenes/mapping.py` (56) | `lookup` is stateful: an in-scene is used once |
| **Algorithm 5**: DecompUpdate | `run_decomp_update` → `_decomp_update` | `src/ighd/update/decomp_update.py` (230, 180) | the new GHD, reusing scene nodes, with the decomposer for the rest |
| Alg 5 line 12, "D(H′, σ)" | `_call_decomposer`, `SceneHintDecomposer` | `src/ighd/update/decomp_update.py` (149, 109) | Algorithm 1 with scene nodes tried first as candidates |
| §3.2 DelVar rule | `delvar_update` | `src/ighd/update/delvar.py` (15) | delete v from every bag |
| **SearchUpdateGHD** (the whole method) | `ghd_update` | `src/ighd/update/pipeline.py` (73) | runs everything above in order and validates the result |

---

## 3. File by file

```
src/ighd/
├── common/            shared vocabulary, no algorithms
│   ├── types.py         Vertex, EdgeName, NodeId; SearchStatus (FOUND / PROVEN_NO / NOT_FOUND),
│   │                    UpdateStatus, Minimality, DecomposerMode (EXACT / HEURISTIC)
│   ├── config.py        Semantics: one switch per paper ambiguity (A2, A3, A16, A17, A21, A23, A28);
│   │                    PAPER_DEFAULT = the readings in the ledger
│   ├── budget.py        Budget(max_expansions, time_limit_s).charge(); running out raises BudgetExhausted
│   └── errors.py        IGHDError and subclasses (InvalidGHDError, NotNormalFormError, ...)
│
├── hypergraph/        the input object
│   ├── core.py          Hypergraph: immutable, NAMED edges {name: frozenset(vertices)};
│   │                    incident(), covered_vertices(), adjacent_to(), induced(), with_edges() ...
│   ├── compare.py       induced_diff(old, new, U, s_delta, mode): Def 4.1(i), edge by edge (A2)
│   └── io_hyperbench.py parse_hyperbench / to_hyperbench
│
├── modifications/     the six classes of §3
│   ├── base.py          ModificationResult(old, new, s_delta, new_edges, new_vertices, removed_vertices)
│   │                    s_delta maps each old edge name to its new name, or None if deleted
│   ├── ops.py           AddVar, DelVar, AddConstr, DelConstr, AddEq, DelEq; each .apply(h) checks
│   │                    its input and the result's invariants (_finish, line 37)
│   └── sequence.py      ModificationSequence / compose: several steps as one δ
│
├── ghd/               the decomposition object and its judges
│   ├── tree.py          GHD: nodes {id: Node(bag, cover, label)}, parent/children, root;
│   │                    preorder, leaves_of, components_without, extract, attach (used by glue)
│   ├── validation.py    validate(h, ghd): edge coverage, connectedness, B ⊆ B(λ)  [independent]
│   └── normal_form.py   check_normal_form: the replay normal form that Def 5.1 requires of scenes
│
├── oracle/            exact references for testing (exponential, small inputs only)
│   ├── ghw_dp.py        exact_ghw(h): DP over elimination orderings with edge-cover numbers (≤ 16 vertices)
│   ├── edge_cover.py    edge_cover_number, minimum_edge_cover
│   └── brute_mutable.py all_mutable_subtrees: every subtree tested against Def 4.1 (≤ 12 nodes)
│
├── static/            ALGORITHM 1
│   ├── separation.py    components(h, edges, U) by union-find; connection(h, comp, U) = V(comp) ∩ U
│   └── decomposer.py    DecompositionTask, DecompResult, TopDownDecomposer, ghw_by_search
│
├── mutable/           ALGORITHM 2
│   ├── conditions.py    mutable_conditions(change, ghd, T*) -> MutabilityCheck (i), (ii), is_subtree
│   └── minimal.py       minimal_mutable_subtree(change, ghd) -> MutableResult(t_star, steps)
│
├── constraints/       THEOREM 4.5 route (strategy THEOREM45)
│   ├── target.py        redecomposition_target: δ(H)* (edges restricted to V*)
│   ├── constraints.py   bag_constraints: one C_i per outer tree
│   └── gluing.py        glue(D*, old, constraints)
│
├── scenes/            ALGORITHMS 3 and 4
│   ├── mapping.py       SceneMapping, SceneEntry(node, IN|OUT, origin), SceneEvent (the decision log)
│   ├── scene_down.py    scene_create (checks NF, then calls _down on the root) and _down = Algorithm 3
│   └── scene_up.py      _up = Algorithm 4 (iterative post-order)
│
├── update/            ALGORITHM 5 and the driver
│   ├── result.py        Strategy (PAPER / THEOREM45 / RECOMPUTE), UpdateTrace, UpdateResult
│   ├── decomp_update.py Fragment tree, delta_bag/delta_cover, reuse checks, _decomp_update = Algorithm 5
│   ├── delvar.py        the DelVar rule
│   └── pipeline.py      ghd_update = SearchUpdateGHD; condition (iii) for composite δ (A26)
│
├── online/            interactive use (not part of the paper)
│   ├── session.py       OnlineSession: holds (H, GHD, k, exact) and applies one modification at a time
│   ├── cli.py           terminal command shell (python online.py)
│   ├── web.py           local HTTP server + JSON API (python web.py)
│   └── static/          index.html, style.css, app.js (the browser page)
└── testing/generators.py  seeded random hypergraphs and modifications for tests and benchmarks
```

---

## 4. What runs, in order, when you apply one modification

This example is the web page's **Apply** button. The terminal, the benchmarks and the tests enter at step ③ or ④.

```
① app.js        $('apply').onclick (line 308) -> request() builds {kind, ...} -> api('/api/modify', ...)
② web.py        Handler.do_POST (249) -> App.handle (152) -> build_modification (101) -> e.g. DelConstr("w7")
③ session.py    OnlineSession.apply (153)
                 ├─ mod.apply(h)                       modifications/ops.py: δ(H) and s_δ, or an error
                 │                                     (nothing changes on an error)
                 ├─ normal form of the current GHD?    if not, use THEOREM45 for this step (Def 5.1)
                 ├─ ghd_update(h, g, mod, k=k, ...)    ④ below
                 ├─ UPDATED  -> _tighten (140): try width k-1, k-2, ... while a GHD is FOUND
                 │   PROVEN_NO -> _raise_from (130): try width k+1, k+2, ... until a GHD is FOUND
                 │   (both use the EXACT decomposer on all of δ(H): our addition, to report ghw itself)
                 ├─ validate(δ(H), new GHD)            never keep an invalid GHD
                 └─ StepReport                          changed edges, kept nodes, timing, ghw note

④ pipeline.py   ghd_update (73) = SearchUpdateGHD
   1. input      validate(H, G); k := width(G); [exact_ghw(H) -> Minimality]          lines 102-113
   2. change     change = modification.apply(H)                                        116
      ├─ strategy RECOMPUTE -> recompute(): Algorithm 1 on all of δ(H)                  156
      ├─ DelVar and fast path -> delvar_update (the paper's rule)                       160
   3. Algorithm 2  t_star = minimal_mutable_subtree(change, G)                          168
      └─ composite δ only: condition (iii), else T* := whole tree (A26)                 171
   4a. strategy THEOREM45:                                                              179
         redecomposition_target -> bag_constraints -> Algorithm 1 on δ(H)* with the
         constraints as coverage-only edges -> glue; if that fails, recompute()
   4b. strategy PAPER (default):                                                        210
         σ = scene_create(change, G, T*)          Algorithms 3 and 4
         run_decomp_update(change, G, k, σ, ...)  Algorithm 5, using Algorithm 1 inside
         fragment_to_ghd(frag)                    assemble the new GHD
   5. finish()   validate(δ(H), out); width ≤ k; normal form noted                      121
                 -> UpdateResult(UPDATED | PROVEN_NO | NOT_FOUND, ghd, trace)
```

`UpdateTrace` records each stage: Algorithm 2's steps, σ and its decision log, every decomposer call, the reused and new nodes, and per-stage timings. The web page, the terminal shell and the benchmarks read their output from it.

---

## 5. Each algorithm's code structure

### Algorithm 1: `static/decomposer.py`

The search state is a pair **(C, conn)**: an edge set C to decompose, and the vertices conn that its root bag must contain.

```
TopDownDecomposer.decompose(task)               333   public entry; returns DecompResult
└─ _decompose                                   344   checks the task, builds H_aug (coverage-only edges),
   │                                                  makes one _Search, catches BudgetExhausted
   └─ _Search.solve((C, conn))                  249   memoised: memo[(C, conn)] = solution or None
      ├─ owner._scene_candidates(...)                 scene hints first (A19; only SceneHintDecomposer has any)
      ├─ _enumerated_candidates(C, conn)        186   every (bag B, cover λ) with |λ| ≤ k, conn ⊆ B ⊆ B(λ),
      │                                               B ∩ W ≠ ∅   (EXACT: all such B; HEURISTIC: maximal B only)
      ├─ _conn_root_candidate                   217   top level only: B = conn (Lemma C′)
      └─ _try(key, B, λ)                        278   for each [B]-component c of C:
                                                        solve((c, connection(c, B)))  <- recursion
   └─ _Search.build(top)                        292   turn the memoised solutions into a GHD tree
```

**Answers:**
- FOUND when a solution is found;
- PROVEN_NO when an EXACT search fails without hitting the budget (Theorem E);
- NOT_FOUND otherwise.

`ghw_by_search` (394) calls it for k = 1, 2, … to get the exact ghw of a fresh hypergraph.

### Algorithm 2: `mutable/minimal.py`

```
minimal_mutable_subtree(change, ghd)            41
  working := all nodes
  repeat (a round):
    for each leaf u of working (by increasing id):            ghd.leaves_of
      check := mutable_conditions(change, ghd, working - {u}) conditions.py:36
               X = union of the bags outside; (i) induced_diff(old, new, X) equal (edgewise);
               (ii) no new vertex adjacent to X
      if (i) and (ii): working -= {u}; start the next round   (I7 asserted: still connected)
  until a round removes nothing -> T* = working
```

### Algorithms 3 and 4: `scenes/`

```
scene_create(change, ghd, T*)                   scene_down.py:127   checks NF (Def 5.1), then:
└─ _down(n = root, H' = E(δ(H)))                 69    Algorithm 3
   ├─ line 3: δ(B_n) not covered by δ(λ_n)?  -> _up(n, H')   (A16)
   ├─ comps := [δ(B_n)]-components of H'
   ├─ line 7: #comps ≠ #children?          -> _up(n, H')
   ├─ line 13: σ[H'] := n  (IN if the subtree of n meets T*, else OUT)
   ├─ lines 14-19: match each child u to a component c with (V(c) − δ(B_n)) ∩ δ(B_u) ≠ ∅
   │               then σ.merge(_down(u, c))        <- recursion down the tree
   └─ line 20: a child matches nothing     -> discard σ and _up(n, H')

_up(node, H')                                   scene_up.py:119   Algorithm 4, post-order
   for each node n (children first): covered := edges of H' inside δ(B_n), plus those covered below;
   if n's subtree avoids T* and the components fit the children: OUT-scene σ[covered] := n
```

### Algorithm 5: `update/decomp_update.py`

```
run_decomp_update(change, old, k, σ, decomposer)       230   top call: (E(δ(H)), conn = ∅)
└─ _decomp_update(run, H', conn)                        180   recursive
   ├─ entry := σ.lookup(H')                     line 5   (stateful: an IN-scene is used once)
   ├─ if entry: u := entry.node                 line 6
   │    bag := δ(B_u), cover := δ(λ_u)                   (A20; restricted if A28 is on)
   │    _reuse_rejection (163): |cover| > k? guard (A16)? conn ⊄ bag (A21)? no progress?
   │    if accepted: for each [bag]-component c of H':      lines 7-10
   │         _decomp_update(run, c, connection(c, bag))     <- recursion
   │       all FOUND -> Fragment(bag, cover, children)      line 11 (old node reused)
   │       a child fails -> fall back (A18) ↓
   └─ _call_decomposer(run, H', conn)           line 12  -> SceneHintDecomposer.decompose(...)
                                                          = Algorithm 1 with scene nodes tried first
```

At the top level a failure always ends in Algorithm 1 on all of δ(H). So a PROVEN_NO from Algorithm 5 is a real proof (MATHEMATICAL_INVARIANTS §6).

---

## 6. A real trace: paper Example 4.3/5.2

The input is H_P2 with the GHD of Fig. 6(a), and δ = DelConstr(w7). This is the actual output of `ghd_update` with the default (PAPER) strategy, read from `UpdateTrace`:

```
Algorithm 2      round 1: leaf u4 removed | round 2: u2 kept, u3 removed | round 3: u1 kept, u2 kept
                 -> T* = {u1, u2}                                    (the paper's answer)
Algorithms 3, 4  A3:L10  u1 is an IN-scene for all of E(δ(H))
                 A3:L16  child u2 matches component {w3, w6}
                 A3:L3   u2 rejected: its δ-cover {w3} no longer covers c  -> Algorithm 4 from u2
                 A4:L16  u4 is an OUT-scene for {w6}
                 A3:L16, A3:L12  child u3 matches {w2, w4}: OUT-scene
                 σ = { E(δ(H)) -> u1 (in),  {w2,w4} -> u3 (out),  {w6} -> u4 (out) }
Algorithm 5      (E(δ(H)), ∅): σ gives u1 -> reuse bag {a,b,c,e,h}, cover {w1,w5}
                   components: {w2,w4} and {w3,w6}
                   ({w2,w4}, {a,h}): σ gives u3 -> reuse bag {a,d,f,g,h}, cover {w2,w4}
                   ({w3,w6}, {e}):   no scene -> Algorithm 1 (1 call): bag {e,i,j,k,l}, cover {w3,w6}
Result           u1 (root) -> u3, new node; width 2; valid; normal form; 2 of 4 old nodes reused
Timings (ms)     input 0.11, modification 0.06, Algorithm 2 0.15, scenes 0.28, Algorithm 5 0.17, validation 0.11
```

To reproduce it, run `python examples/walkthrough.py`, or on the web page load "Paper H_P2" and delete w7. The web page uses an exact-search decomposition as its starting point, not the paper's Fig. 6(a), so its numbers differ.

---

## 7. The other strategies and entry points, in one line each

- **THEOREM45:** Algorithm 2, then `redecomposition_target`, then `bag_constraints`, then Algorithm 1 on δ(H)\* with the constraints as coverage-only edges, then `glue`. It needs no normal form.
- **RECOMPUTE:** Algorithm 1 on all of δ(H). This is the paper's "Classic" baseline in the benchmarks.
- **`benchmarks/worker.py: run_task`** (132) calls `ghd_update` with PAPER for Update and with RECOMPUTE for Classic, in a separate process with a hard time limit.
- **`online/cli.py`** (terminal) and **`online/web.py`** (browser) both drive `OnlineSession`.
- **Tests:**
  - `tests/unit` cover one module each;
  - `tests/paper_examples` replay the paper;
  - `tests/dynamic_updates`, `tests/randomized` and `tests/online` run `ghd_update` or `OnlineSession` and check every answer against `oracle/`.

## 8. Data passed between stages

| Object | Created by | Consumed by |
|---|---|---|
| `Hypergraph` | user input, `parse_hyperbench`, `Modification.apply` | everything |
| `ModificationResult` (old, new, **s_δ**, new vertices) | `Modification.apply` | Algorithm 2, the scenes, Algorithm 5 (`delta_bag`/`delta_cover` map old bags and covers into δ(H)) |
| `GHD` | the decomposer (`_Search.build`), `fragment_to_ghd`, `glue` | the validator, Algorithms 2–5, the drawings |
| `MutableResult` (T\*, steps) | Algorithm 2 | the scenes, the Theorem 4.5 route, the trace |
| `SceneMapping` σ | Algorithms 3–4 | Algorithm 5 (`lookup`), `SceneHintDecomposer` (`peek`) |
| `Fragment` tree | Algorithm 5 | `fragment_to_ghd`, which assembles the GHD once at the end |
| `UpdateResult` + `UpdateTrace` | `ghd_update` | `OnlineSession`, the benchmarks, the tests |

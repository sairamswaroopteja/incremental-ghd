# PAPER_ANALYSIS — Incremental Updates of Generalized Hypertree Decompositions

**Primary source.** G. Gottlob, M. Lanzinger, D. M. Longo, C. Okulmus, *Incremental Updates of Generalized Hypertree Decompositions*, arXiv:2209.10375v1 (21 Sep 2022), 27 pages. Local copy: `Downloads/2209.10375v1.pdf`. All page and section references below are to this version.

**Secondary source.** `../Incremental_GHD_Updates_Guide.pdf` (our study guide). Every statement here was re-checked against the PDF. Where the guide added interpretation, it is marked **[interp]**.

**Not consulted.** The journal version (ACM JEA 27, Art. 1.16, 2023) and the BalancedGoUpdate source code (github.com/cem-okulmus/BalancedGoUpdate). Both could settle the ambiguities in §4 and are listed as investigation items there.

Labels used throughout: **[P]** stated in the paper; **[P-impl]** implied by the paper's proofs or examples; **[interp]** our reading; **[bg]** standard background not in the paper.

---

## 1. Definitions

| ID | Concept | Paper | Statement (paraphrased) | Implementation implication |
|---|---|---|---|---|
| D1 | CSP | §2.1 | $\langle V, D, C_t\rangle$; a constraint is $(s_i, r_i)$, scope plus relation | Only scopes matter. We never store relations. |
| D2 | Hypergraph | §2.1 | $H = (V(H), E(H))$, $E(H) \subseteq 2^{V(H)}$, edges **non-empty**, **no isolated vertices** w.l.o.g. "$H$" often denotes $E(H)$ | Edges are non-empty sets, and $V(H)$ is derived as the union of the edges [interp, as in `dtw/hyper` D2]. Edges carry **names** ($w_1, \ldots$), which the paper uses throughout. |
| D3 | Subhypergraph | §2.1 | a subset of the edges $H' \subseteq H$ | Scene keys and components are **sets of edge names**. |
| D4 | Induced subhypergraph | §2.1 | $V(H[U]) = U$, $E(H[U]) = \{e \cap U \mid e \in E(H)\}$ | Empty intersections must be dropped [interp, see A1]. Comparisons need a defined edge identity (A2). |
| D5 | $B(E)$ | §2.2 | $B(E) = \bigcup_{e\in E} e$ | Helper function. Also used for trees: $B(T') = \bigcup_{u\in T'} B_u$. |
| D6 | GHD | §2.2 | $\langle T, (B_u), (\lambda_u)\rangle$, $T$ a tree, $B_u \subseteq V(H)$, $\lambda_u \subseteq E(H)$: **(1)** every **edge** $e$ satisfies $e \subseteq B_u$ for some $u$; **(2)** for every vertex $v$, $\{u \mid v \in B_u\}$ is connected; **(3)** $B_u \subseteq B(\lambda_u)$ | The validator checks exactly these three. ⚠ Condition (1) is **edge** coverage. "Vertex coverage" follows from it given no isolated vertices, but is weaker, so the validator must check edge coverage. |
| D7 | width, ghw | §2.2 | width $= \max_u |\lambda_u|$; ghw $=$ min over all GHDs | Width counts **guard edges**, never bag size. |
| D8 | $T_u$, $V(T_u)$ | §2.2 | the subtree rooted at $u$ and the union of its bags | Needs a rooted view of $T$. A GHD is unrooted by definition, so rooting is extra structure, required by Algorithm 1 and the scenes. |
| D9 | [U]-adjacency, [U]-connectedness, [U]-component | §2.3 | edges $e_1, e_2$ are [U]-adjacent iff $(e_1\cap e_2)\setminus U \ne \emptyset$; a component is a maximal [U]-connected **set of edges**; [S] for an edge set $S$ means $U = \bigcup S$; size $= \lvert C\rvert$ | This is defined on **edges**, not on vertices of the primal graph. Edges with $e \subseteq U$ are excluded [P-impl, Examples 2.3 and 5.2; A3]. |
| D10 | Normal form | §2.3 (citing [13]) | for root $u$ with $[B_u]$-components $C_1..C_\ell$: $u$ has $\ell$ children $u_i$, and every $e \in C_i$ is covered (contained in a bag) inside $T_{u_i}$ | Needed as a **precondition** of scene creation (Def. 5.1). A checker is required, and a normaliser is optional (A15). |
| D11 | Modification | Def. 3.1 | any function from hypergraphs to hypergraphs | Framework code (Lemma 4.2, Lemma 4.4, Thm 4.5) must accept *any* modification object that supplies $\delta(H)$, $s_\delta$ and $V_{new}$. |
| D12 | AddVar / DelVar | Def. 3.2 | AddVar: new $w$ added to the edges $E' \ne \emptyset$ (so $(E, E')$ partitions $E(H)$). DelVar: $v$ removed from all edges | "$V \cup w$" should read $V \cup \{w\}$ (typo). DelVar may empty an edge, which then disappears (A6). |
| D13 | AddConstr / DelConstr | Def. 3.3 | $H \cup \{f\}$ with $f \notin E(H)$; $H \setminus \{e\}$ | Is $f \subseteq V(H)$ required? Not stated; the experiments use only existing vertices (§6.1). DelConstr can isolate vertices (A7). |
| D14 | AddEq / DelEq | Def. 3.4 | AddEq: $U$ merged into $w \in V(\delta(H))$, and the edges $E_U$ now contain $w$. DelEq: $w$ split into $U$, with the edges of $E_{\{w\}}$ "arbitrarily distributed" | It is not specified whether $w \in U$ (AddEq) or which part keeps the old name (DelEq). This determines $V_{new}$ and therefore $T^*$ (A8). Merging can make two edges identical (A9). |
| D15 | SearchUpdateGHD(Δ) | §3.2 | input: $H$, $\delta \in \Delta$, a **minimal-width** GHD of $H$; output: a GHD of $\delta(H)$ with width $\le \text{ghw}(H)$, or "no" | Search problem. "no" ⇔ $\text{ghw}(\delta(H)) > \text{ghw}(H)$. Minimality of the input must be **verified or flagged** (A14). |
| D16 | Polynomially captures | §3.2 | Δ captures Δ′ if every $\delta' \in \Delta'$ can be reproduced by a polynomial-length Δ-sequence along which ghw never decreases | Theory only; not implemented. |
| D17 | $T \setminus T'$, $H[T']$ | §4.1 | the forest left after deleting $T'$; $H[T'] := H[\bigcup_{u\in T'} B_u]$ | Needs forest decomposition and union-of-bags helpers. |
| D18 | δ-mutable subtree | Def. 4.1 | a subtree $T^*$ with (i) $H[T\setminus T^*] = \delta(H)[T\setminus T^*]$ and (ii) no $v \in V(\delta(H))\setminus V(H)$ adjacent in $\delta(H)$ to a vertex of $B(T\setminus T^*)$ | Exact condition checker (A2, A10). Applies to arbitrary δ. |
| D19 | $\delta(H)^*$ | §4.1 | the part of $\delta(H)$ containing $\delta(H)[T^*]$ **plus** any new vertices and edges | [interp] vertices $V^* = \delta(B(T^*)) \cup V_{new}$; edges = non-empty $e \cap V^*$ for $e \in E(\delta(H))$ (A11). |
| D20 | Bag constraint; $T^*$-induced constraints | §4.1 | a set $C \subseteq V(\delta(H)^*)$ is satisfied if $C \subseteq B_u$ for some node; for the outer nodes $u_1..u_q$ adjacent to $T^*$: $C_i = B_{u_i} \cap B(T^*)$ | Exactly one constraint per outer tree [interp, proof in guide §6.6]. |
| D21 | $s_\delta$, $\delta(X)$, $\delta(Y)$ | §5.1 | $s_\delta : E(H)\to E(\delta(H))\cup\{\emptyset\}$; $\delta(X) = \{s_\delta(e)\}$; $\delta(Y) = Y \cap V(\delta(H))$ | Every modification must output $s_\delta$ explicitly. This is our edge-identity mechanism (A2). |
| D22 | Scene mapping, in/out-scene | Def. 5.1 | a partial map $\sigma : 2^{E(H)} \to N(T)$ for a **normal-form** GHD; out-scene iff $\sigma(H') \notin T^*$ | Dictionary from `frozenset[EdgeName]` to node id, plus a kind flag and a "consumed" flag for in-scenes. |

## 2. Results and how they depend on each other

```
[11] 3-SAT → ghw≤2 reduction ──► Thm 3.6 (hardness: AddEq, DelEq, AddVar, AddConstr, DelConstr)
                                   └─► Cor 3.7 (classes that polynomially capture these)
footnote 1 (induced subhypergraphs never increase ghw) ──► DelVar is trivial (§3.2, §6.1)

[bg] separation property of tree decompositions ─┐
[bg] "gate node" / Helly property of subtrees ───┼─► Lemma 4.2 (outer subtrees stay GHDs of δ(H)[T'])
Def 4.1 ─────────────────────────────────────────┘          │
                                                            ├─► Lemma 4.4 (minimal T* is unique; Alg 2 finds it)
                                                            └─► Thm 4.5 (gluing: GHD of δ(H)* + constraints ⇒ ghw(δ(H)) ≤ k)
Def 5.1 + Lemma 4.2 ─► out-scenes are safe to reuse ─► Alg 3/4 (scene creation) ─► Prop 5.3 (O(N³))
                                                                                └─► Alg 5 (GHDUpdate)
[13] normal-form theorem ─► Alg 1 is complete; scene replay is meaningful
```

| Result | Statement | Proof relies on | What the implementation must honour |
|---|---|---|---|
| Thm 3.6 | SearchUpdateGHD(Δ) is not in P for the five classes, unless P = NP | Appendix A: the $H_\varphi$ gadget of [11], with many-one reductions for DelConstr/DelEq and Turing reductions for AddVar/AddConstr/AddEq | No polynomial update-time claim. Exact negative answers need exhaustive search. |
| Cor 3.7 | Hardness carries over to classes that polynomially capture these | Thm 3.6 | Documentation only. |
| DelVar (fn. 1, §6.1) | Deleting $v$ from every bag gives a GHD of width $\le k$ | induced subhypergraph | O(size of GHD) fast path. The output may not be optimal (A14). |
| Lemma 4.2 | every tree $T'$ of $T\setminus T^*$, with its old labels, is a GHD of $\delta(H)[T']$ (guards read as $e \cap B(T')$, fn. 2) | restricting induced subhypergraphs; the "gate" argument [P-impl: "must have a common node"] | Outer subtrees are copied verbatim. Property test: validate each outer tree against $\delta(H)[T']$. |
| Lemma 4.4 | the minimal δ-mutable subtree is unique, and Alg 2 computes it in polynomial time | uniqueness via $T_2\setminus X$; the union step needs the edge-wise reading (A2) | Brute-force oracle: enumerate all subtrees of a small $T$, filter by Def 4.1, check that the minimum is unique and equals Alg 2's output. |
| Thm 4.5 | if $\delta(H)^*$ has a GHD of width $\le k$ satisfying all $T^*$-induced constraints, then gluing gives a GHD of $\delta(H)$ of width $\le k$ | Lemma 4.2, the separation property, condition (ii) (implicit) | Gluing procedure; the validator must accept every glued result. A **sufficient** condition only, so failure ⇏ "no". |
| Prop 5.3 | scene creation runs in $O(N^3)$ | linear-time components (Tarjan [27]), at most N nodes [interp] | Implement without hidden super-cubic steps; measure it. |

## 3. Algorithms

### Algorithm 1: schematic top-down GHD construction (p. 5)
`FindDecomp(H')` loops over `sep ∈ Separators(H', k)`. For each it picks a cover with $|\lambda| \le k$ and `sep ⊆ B(cover)`, where the cover edges may come from **all** of $E(H)$. It computes the [sep]-components, recurses on each, and on any failure moves to the next `sep`. If no separator works it returns Reject.
- **Omitted by the paper:** the *connection set*. For gluing to be valid, a child's root bag must contain $V(c) \cap B_{parent}$ [interp, standard in det-k-decomp] (R1).
- **Base case** [P-impl, Ex. 2.3]: a component with $|C| \le k$ can be one node with $B = B(C)$ and $\lambda = C$.
- `Separators` is left implementation-specific. Our exact enumeration is described in IMPLEMENTATION_PLAN §C S7.
- **Why our exact search space is complete [interp, to be re-proved in MATHEMATICAL_INVARIANTS.md before S7].** The state is $(C, conn)$ with $W = V(C)\setminus conn$. The search picks $\lambda \subseteq E(H)$ with $|\lambda|\le k$, and a bag $B$ with $conn \subseteq B \subseteq B(\lambda)\cap(W\cup conn)$ and $B\cap W\ne\emptyset$, then recurses on the $[B]$-components $C_i$ with $conn_i = V(C_i)\cap B$.
  1. By the normal-form theorem the paper cites ([13], §2.3), a width-$\le k$ GHD can be assumed to have one child subtree per component.
  2. Within the subtree for $C$, deleting every vertex outside $W \cup conn$ from all bags keeps a valid decomposition of $C$. Coverage holds because no edge of $C$ contains such a vertex. Connectedness holds because occurrence sets are intersected with a subtree. The guard condition holds because bags only shrink. Width does not grow.
  3. The child's root must contain $conn$, or connectedness fails across the parent edge.
  4. The NF progress condition (GLS NF2) gives $B \cap W \ne \emptyset$, so $|W|$ strictly decreases and the recursion terminates.
  5. Exactness needs **all** subsets $B$, not just $B(\lambda)\cap(W\cup conn)$. The latter is the HD/det-k-decomp choice and is incomplete for ghw: that is exactly the difference between ghw and hw.
- **Exact-width oracle (independent of the search above) [bg].** $\text{ghw}(H) = \min$ over tree decompositions of $\max_u \rho_H(B_u)$, where $\rho_H$ is the integral edge-cover number. Because $\rho_H$ is monotone under subsets, and every tree decomposition can be refined to one from a minimal triangulation whose bags are subsets of the original bags, the minimum is attained over elimination orderings. That allows a subset dynamic programme over vertex sets.

### Algorithm 2: minimal δ-mutable subtree (p. 12)
Start with $T' = T$ and $V_{new} = V(\delta H)\setminus V(H)$. Repeat: for each leaf $u$ of $T'$, let $T'_{-u} = T' \setminus \{u\}$, $A = H[T\setminus T'_{-u}]$ and $B = \delta(H)[T\setminus T'_{-u}]$, and let Adj be the set of vertices adjacent in $\delta(H)$ to $B(T \setminus T'_{-u})$. If $A = B$ and $V_{new}\cap \text{Adj} = \emptyset$, set $T' := T'_{-u}$ and break. Stop when nothing changes.
- The leaf order is unspecified. Under edge-wise semantics the result is order-independent (Lemma 4.4). We still fix a deterministic order (sorted node ids) for reproducibility.
- **Single remaining node / empty result** is not discussed (A12).

### Algorithm 3: SceneCreationDown (p. 15)
- **L3:** if $\delta(B_n) \not\subseteq B(\delta(\lambda_n))$, go upward.
- **L5–8:** set $sep = \delta(B_n)$ and compute comps; if $|comps| \ne |children|$, go upward.
- **L9–12:** in-scene if $T_n \cap T^* \ne \emptyset$, otherwise out-scene, keyed by $H'$.
- **L14–20:** for each child, take the first component $c$ with $(V(c)\setminus\delta(B_n))\cap\delta(B_u) \ne \emptyset$ and recurse. If no component matches the child (the inner loop ends without break), discard everything and go upward.
- **Example 5.2 conflicts with L3** (A16).

### Algorithm 4: SceneCreationUp (p. 16)
Post-order traversal accumulating `coveredBelow`. If $T_n \cap T^* = \emptyset$: add the edges $e \in E(H')$ with $e \subseteq B_n$, set $sep = B_n$, compute the [sep]-components of `coveredEdges`, and if $|comps| = |children|$ record an out-scene. Return $(\sigma, \text{coveredEdges})$.
- **Key inconsistency** (A17): line 16 records "$H'\mapsto sep$", while the text says the key is $H[T_n]$, and the text and pseudocode disagree on what $H[T_n]$ means.
- **L13** uses $B_n$ without applying δ, justified outside $T^*$.

### Algorithm 5: GHDUpdate / DecompUpdate (p. 17)
Compute $\sigma$ = SceneCreationDown(root, $H$, $T^*$), then call `DecompUpdate(H', σ)`. If $\sigma(H')$ is defined (a **stateful** lookup: in-scenes are reported only once), set $u = \sigma(H')$, compute comps = $[u.Bag]$-components of $H'$, reset $u.Children$, and recurse on each comp. Otherwise call the decomposer $D(H', \sigma)$.
- Not specified: rejection propagation (A18), the scene's interface with the parent (R1), and how $D$ consumes $\sigma$ (A19).
- **L7** uses `u.Bag` without δ (A20).

## 4. Ambiguities, inconsistencies and how we will pin each one down

Each item gets a decision, a switch in the code where it matters, and a **pinning test**: a minimal test that records the behaviour of each reading.

| # | Issue | Evidence | Options | Proposed resolution | Pinning test |
|---|---|---|---|---|---|
| A1 | Empty intersections in $H[U]$ | Def. §2.1 writes $\{e\cap U\}$ but edges must be non-empty | keep ∅ or drop it | **Drop** | `H[U]` never contains an empty edge |
| A2 | Equality "$H[X] = \delta(H)[X]$": as **sets of vertex-sets**, or **edge by edge** via $s_\delta$? | Lemma 4.4's union step is valid only edge-wise (counterexample: $\{y,z\}$ vs $\{y\},\{z\}$); §5.1 introduces $s_\delta$ | `SET` / `EDGEWISE` | **Default EDGEWISE** (matches named edges and the proof). `SET` is kept as an option for differential study | (a) the counterexample; (b) all paper and guide examples give identical $T^*$ under both; (c) the random search reports instances where they differ |
| A3 | Edges $e \subseteq U$ as singleton [U]-components? | The literal definition makes them components; Examples 2.3 and 5.2 do not count them | include / exclude | **Exclude** (they are covered by the separator) | `components(H_{P'}, {c,e,h,i,k}) == [{w1,w2,w4},{w6}]` |
| A4 | Vertex vs edge coverage in GHD condition (1) | §2.2 condition (1) is edge coverage | — | Validate **edge** coverage. Vertex coverage is reported as a derived diagnostic | a GHD covering all vertices but not edge $\{a,b\}$ is rejected |
| A5 | AddVar typo "$V(H)\cup w$" | Def. 3.2 | — | read as $\cup\{w\}$; require $E' \ne\emptyset$ and $w \notin V(H)$ | invalid input raises |
| A6 | DelVar empties a singleton edge | not discussed | drop the edge / keep ∅ | drop it, with $s_\delta(e) = \emptyset$ | DelVar on $\{v\}$ |
| A7 | DelConstr leaves isolated vertices | the paper assumes none w.l.o.g. | keep them / drop them | **Drop**: $V(\delta H)$ is derived from the edges, and the dropped vertices are recorded as removed | delete $w_6$ from $H_{P'}$ → $j, l$ vanish |
| A8 | AddEq: is $w \in U$? DelEq: which part is "new"? | Def. 3.4; Ex. 3.5 merges $b$ into $g$ ($w = g \in U$) | — | The modification object names $w$ and the new parts **explicitly**; $V_{new}$ follows from the names | `test_a8_merge_target_inside_or_outside_u_changes_t_star` (same merge, $w\in U$ gives $T^*=\{n_1\}$, $w\notin U$ gives $T^*=T$); also S2 `test_addeq_into_fresh_vertex` and S13 `test_generator_gaps.py` |
| A9 | Two edges become identical after AddEq/DelVar/DelEq | $E$ is a *set* in the paper | merge them (multi-map $s_\delta$) / keep both names | **Keep both names** (ghw is unaffected by duplicate edges; covers stay well-defined) and flag `has_duplicate_edges`. Recorded in the ledger | merge $b, c$ in $\{a,b\},\{a,c\}$ |
| A10 | "Adjacent to $B(T\setminus T^*)$": does a vertex count as adjacent to itself? | Def. 4.1(ii) | — | adjacency means sharing an edge; new vertices are never in old bags, so this cannot matter | — |
| A11 | Precise vertex and edge sets of $\delta(H)^*$ | §4.1 prose | — | D19 reading; condition (ii) guarantees every edge containing a new vertex lies entirely inside $V^*$ (asserted at runtime) | assertion test |
| A12 | Empty $T^*$ (δ invisible from all bags, e.g. AddConstr of an edge made only of new vertices) | not discussed | — | Allowed. If $T^* = \emptyset$ the old GHD is valid for the old part, and new parts are attached as a separate decomposition joined by an arbitrary tree edge (no shared vertices). [interp] | edge of fresh vertices |
| A13 | Algorithm 1 has no connection set | p. 5 | — | the decomposer takes `conn` explicitly (standard) | Example 2.3 replay |
| A14 | SearchUpdateGHD needs a **minimal** input GHD; outputs need not be minimal | §3.2; DelVar | — | `UpdateInput.minimality = VERIFIED / ASSUMED`; the exact oracle verifies it on small instances | DelVar on $H_{P'}$ → width 2 while ghw = 1 |
| A15 | Scenes need **normal form**; old GHDs may not be in NF | Def. 5.1 | reject non-NF / normalise | Stage 1: check and **reject** with a clear error. A normaliser is a later stage (R6) | the Fig. 6a GHD passes the NF check |
| A16 | **Example 5.2 vs Alg 3 L3**: the example maps $C_2\mapsto u_2$, but L3 fails at $u_2$ after $w_7$ is deleted ($c \notin B(\{w_3\})$) | pp. 15, 17 | literal pseudocode / example | **Literal pseudocode** by default. The example's mapping would yield an invalid guard. Both behaviours are pinned | test asserts our $\sigma$ = {H→u1 (in), C3→u3 (out), {w6}→u4 (out)}, and that forcing the paper's $\sigma$ makes the validator reject the result |
| A17 | **Up-phase scene key**: L16 says "$H' \mapsto sep$" ($H'$ unchanged from the parent); the text says "$H[T_n] \mapsto u$"; the text defines $H[T_n]$ as edges *intersecting* $V(T_n)$, while lines 10–14 collect edges *covered* in $T_n$ | pp. 14–16 | `LITERAL_H_PRIME` / `COVERED_EDGES` / `INTERSECTING_EDGES` | **COVERED_EDGES** (matches the L14 comment), with the others selectable. LITERAL makes every upward scene in a subtree share one key and can break connectedness | pinned on Example 5.2: LITERAL maps C2→u4, and forcing its use yields a validator error |
| A18 | DecompUpdate: what happens when a recursive call rejects? | p. 17 prose: in-scenes "used at most once", "never harm correctness" | — | if any child fails under a reused node, fall back to $D(H', \sigma)$ for $H'$ (the in-scene is already consumed); rejection propagates otherwise | crafted in-scene failure |
| A19 | How the decomposer uses $\sigma$ | p. 17–18: "trivial", details not given | — | the decomposer tries scene nodes **first** as candidate separators, then continues the full search (keeps exactness) | exact mode returns identical yes/no with and without σ |
| A20 | DecompUpdate L7 uses `u.Bag`, not $\delta$(`u.Bag`) | p. 17 | — | use $\delta(B_u)$ and $\delta(\lambda_u)$ (identical for out-scenes) | DelVar-style test |
| A21 | Scene reuse and the **parent interface** | not addressed | — | a scene node $u$ is reusable for component $c$ only if $conn(c) \subseteq \delta(B_u)$. This is the top-down form of the bag constraints. Never skipped | crafted case where conn ⊄ B_u |
| A22 | Theorem 3.6 proof idea swaps ghw 2 and 3 | p. 9 vs App. A.2 | — | the appendix is correct (ghw 2 ⇔ satisfiable) | doc only |
| A23 | Matching in Alg 3 L16 need not be injective | p. 15 | — | additionally require a bijection, otherwise go upward. **Deviation, ledger entry**: it only reduces reuse and never changes correctness | crafted |
| A24 | Table 1 timeout semantics (exclusive vs total) | p. 19–21 | — | report both in our benchmarks | done: `benchmarks/metrics.py` reports exclusive and total timeouts per system (S14) |
| A25 | **In/out kind of a scene at an ancestor of $T^*$**: Def 5.1 says in-scene iff $\sigma(H')\in T^*$; Alg 3 line 9 says in-scene iff $T_n \cap T^* \ne \emptyset$, which also covers ancestors of $T^*$ outside it | Def 5.1 vs Alg 3 L9 (p. 14–15) | Def reading / pseudocode reading | **Pseudocode** (in-scene, single use). Conservative: it only limits reuse, never correctness. Found in the W4 review | an S11 test where the root lies outside $T^*$ but above it gets IN |
| A26 | **Theorem 4.5 fails for arbitrary modifications**, although §4 says its results apply to any modification (Def 3.1). Counterexample (Agent D, verified by the main agent): $H=\{e_1{:}ab, e_2{:}bc\}$, tree $u_1(ab)-u_2(bc)$, δ adds the *existing* vertex $c$ to $e_1$. $T^*=\{u_2\}$ satisfies Def 4.1 and Alg 2 returns it, but the glued GHD leaves $e_1'=\{a,b,c\}$ uncovered. The proof's step "an edge of δ(H) not in δ(H)* is in H" is false for an edge that changes by *existing* vertices only. **Reachable with our ModificationSequence**: AddVar(z into $e_1$) then AddEq({z,c} → c) | §4 intro (p. 10), Thm 4.5 proof (p. 13) | restrict to elementary δ / add a third condition / fall back | **Theorem 4.5 holds for each of the six elementary classes** (proof per class: MATHEMATICAL_INVARIANTS §4). For any other δ (sequences, custom functions), the update checks condition (iii): every new or changed edge of δ(H) lies inside $V^* = \delta(B(T^*))\cup V_{new}$. If it fails, $T^*$ falls back to the whole tree (always valid; no reuse). Decided; implemented in S12 | `test_thm45_fails_for_a_general_modification` (S10); S12 sequence test |
| A27 | σ maps the same edge set at a node and at its child (Def 5.1 says σ is a function) | Alg 3 L13 vs L17–18 | — | deeper entry wins; replacement logged (S11) | S11 test |
| A28 | Alg 5 L6 reuses u as is; its bag may contain vertices outside V(H′) ∪ conn | p. 17 | literal / restrict | **literal** default; restriction available (sound by Lemma H). No invalid output observed under the literal default | S12 `test_a28_restricting_reused_bags_masks_a16` |
| A29 | The DelVar rule's output need not be in normal form, which Def 5.1 requires of the next update's input (the paper does not discuss chaining) | §3.2, §6.1 vs Def 5.1 | — | keep the paper's rule; `delvar_fast_path=False` option; NF reported in every result. 31% of random DelVar outputs were not NF | `test_a29_delvar_rule_output_is_not_normal_form_and_breaks_chaining` (paper_discrepancy) |
| A21+ | **Evidence that A21 is required**: under the paper's default readings, literal Alg 5 without the interface check returned invalid GHDs in 37/3000 random updates, including a wrong YES (width-1 output for a hypergraph of ghw 2) | Alg 5 | — | interface check always on by default | `test_a21_interface_check_is_required_by_the_paper_algorithm` |

## 5. Implementation implications (summary)

1. **Named edges with an explicit $s_\delta$** are the backbone. Algorithm 2, scenes and Lemma 4.2 all need edge identity.
2. Three different hypergraph views must never be conflated: the **subhypergraph** (an edge set; components and scenes), the **induced subhypergraph** (restricted edges; Def. 4.1, Lemma 4.2), and the **re-decomposition target** $\delta(H)^*$.
3. Guards are always drawn from the full $E(\delta(H))$, even when decomposing $\delta(H)^*$ (Alg. 1 L5 and Thm 4.5 both use full edges).
4. Bag constraints have two equivalent realisations. *Coverage-only pseudo-edges* $C_i$ (must be covered, may not guard) give the Theorem 4.5 route. The *connection set* gives the top-down route. Both are implemented.
5. **Exactness is a property of the search, not of the output.** A "no" is reported as `PROVEN_NO` only after an exhaustive exact search of $\delta(H)$ at width $k$. Everything else is `NOT_FOUND`.
6. The width bound $k$ is fixed to the input width, and the result records whether input minimality was verified.

## 6. Experimental protocol to reproduce (§6)

- **Data:** HyperBench (1798 of 2035 instances with known optimal ghw).
- **Modifications:** five per class per hypergraph. AddVar: $\lceil\text{avg degree}\rceil$ random edges. AddEq: merge two random vertices. DelEq: split $x$ into $y_1, y_2$, half of the edges each. AddConstr: a new edge of $\lceil\text{avg rank}\rceil$ existing vertices. DelConstr: a random edge. DelVar is excluded.
- **Systems:** *Update* vs *Classic* (the same decomposer run from scratch). htdLEO is out of scope.
- **Filter:** report instances where Classic takes more than 15 ms. Timeout 30 min, 1 core, 1 GB.
- **Metrics:** Positive %, Better %, geometric-mean times, geometric-mean speed-up, timeouts. Runtime by ghw, number of edges and number of vertices (Fig. 7).
- Absolute numbers will not match (different decomposer and machine); we reproduce the **comparison protocol**.

# MATHEMATICAL_INVARIANTS

This document states the invariants the implementation relies on and proves the ones that are
**not** proved in the paper. Results the paper proves (Lemma 4.2, Lemma 4.4, Theorem 4.5) are
listed with the exact property the code must preserve. Proof expansions for those are in the study
guide, §6.

Notation: $H$ is a hypergraph with named edges. $B(E) = \bigcup E$. A decomposition is a rooted tree
with bags $B_u$ and covers $\lambda_u$. "Good" is defined in §2.

---

## 1. Invariants used across the code

| # | Invariant | Source | Checked by |
|---|---|---|---|
| I1 | Every GHD handed to or returned by an update is a GHD of the right hypergraph: conditions (1)–(3) | paper §2.2 | `ghd.validation.validate` after every update |
| I2 | An update input has width $k$; when verified, $k = \text{ghw}(H)$ | paper §3.2 | oracle (`Minimality`) |
| I3 | A scene-creation input is in replay normal form (`ghd.normal_form` docstring) | Def 5.1 | `check_normal_form` |
| I4 | Every tree of $T\setminus T^*$, with unchanged labels, is a GHD of $\delta(H)[T']$ (guards read as $e\cap B(T')$) | Lemma 4.2 | property test (S9) |
| I5 | Every tree of $T\setminus T^*$ meets $T^*$ by exactly one tree edge, and its interface is $C_i = B_{u_i}\cap B(T^*)$ | tree argument (guide §6.6) | assertion in `bag_constraints` |
| I6 | Every cover has at most $k$ edges, and no cover is ever enlarged | Thm 4.5 (W) | validator width (≤ k); directly: `tests/randomized/test_invariants_i6_i7.py` checks that every reused node's cover equals δ(λ_u) under PAPER (literal and restricted) and THEOREM45 |
| I7 | The working tree of Algorithm 2 is δ-mutable at every step | Lemma 4.4 | runtime assertion in `mutable.minimal` (connectedness of each accepted working tree; conditions (i) and (ii) are the acceptance test itself); `tests/randomized/test_invariants_i6_i7.py` replays the step log and checks every intermediate working tree against the brute-force oracle |
| I8 | Every edge of $\delta(H)$ that contains a new vertex lies inside $V^*$ | Def 4.1(ii) ⇒ D19 | assertion in `redecomposition_target` |
| I9 | A scene node $u$ roots component $c$ only if $conn(c) \subseteq \delta(B_u)$ and $\delta(B_u)\subseteq B(\delta(\lambda_u))$ | A21, Alg 3 L3 | reuse check in `update.decomp_update._reuse_rejection` (a failed check rejects the scene, it is not an assertion); holds only while `scene_guard_check` and `scene_interface_check` are on (the defaults) |
| I10 | `PROVEN_NO` is produced only by an unbudgeted EXACT search over all of $\delta(H)$ at width $k$ | §A.1.4 of the plan | unit tests in S7 and S12 |

---

## 2. The exact top-down search: soundness, completeness, termination (needed before S7)

### 2.1 Setting

The input is a hypergraph $H$ (whose edges form the **guard pool**), a set $K$ of named
**coverage-only** vertex sets, and $k \ge 1$. Write $\mathcal{E} = E(H) \cup K$ for the sets that must be
covered. A **constrained GHD** is a tree decomposition of $\mathcal{E}$ (every $e\in\mathcal{E}$ lies
inside some bag, and every vertex's occurrences are connected) with covers
$\lambda_u \subseteq E(H)$, $|\lambda_u|\le k$ and $B_u\subseteq B(\lambda_u)$.

With $K=\emptyset$ this is exactly a GHD of $H$ of width $\le k$. With $K$ equal to the $T^*$-induced bag
constraints, it is a GHD satisfying those constraints (Theorem 4.5's hypothesis).

A **state** is a pair $(C, conn)$ with $C \subseteq \mathcal{E}$ and $conn\subseteq V(C)$. Set $W = V(C)\setminus conn$.
A decomposition $D$ is **good for $(C,conn)$** if it is a tree decomposition of $C$ with covers as above,
and $conn \subseteq B_{root(D)}$.

**Search step `S(C, conn)`.** Enumerate every $\lambda\subseteq E(H)$ with $1\le|\lambda|\le k$ and
$conn\subseteq B(\lambda)$. For each, enumerate every bag $B$ with
$$conn \subseteq B \subseteq B(\lambda)\cap(W\cup conn), \qquad B\cap W\ne\emptyset .$$
Let $C_1..C_\ell$ be the $[B]$-components of $C$ (edges with a vertex outside $B$, grouped by sharing such
vertices), and $conn_i = V(C_i)\cap B$. If every $S(C_i, conn_i)$ succeeds with $D_i$, return the root
$(B, \lambda)$ with children $D_1..D_\ell$. The top-level call is $S(\mathcal{E}, \emptyset)$.

### 2.2 Lemma A (termination)

$|V(C_i)\setminus conn_i| < |W|$.

*Proof.* $V(C_i)\setminus conn_i = V(C_i)\setminus B \subseteq V(C)\setminus B$. Since $conn\subseteq B$, this
is contained in $W\setminus B$, which is a proper subset of $W$ because $B\cap W\ne\emptyset$. ∎

### 2.3 Lemma B (soundness: every output is good, and its bags lie inside $V(C)$)

By induction on $|W|$. Let the output have root $(B,\lambda)$ and children $D_i$. By induction, each $D_i$ is good for
$(C_i, conn_i)$ and has all bags inside $V(C_i)$.

- **Guards and width:** at the root by choice of $\lambda$ and $B$; in each $D_i$ by induction.
- **Coverage:** an $e\in C$ with $e\subseteq B$ is covered at the root. Any other $e$ has a vertex outside $B$, so it lies in exactly one $C_i$ and is covered in $D_i$.
- **$conn$:** $conn \subseteq B$, the root bag.
- **Bags inside $V(C)$:** $B \subseteq W\cup conn = V(C)$, and $V(C_i)\subseteq V(C)$.
- **Connectedness**, for a vertex $v$:
  - If $v$ occurs in $D_i$ and $D_j$ with $i\ne j$: then $v\in V(C_i)\cap V(C_j)$. A shared vertex outside $B$ would make $C_i$ and $C_j$ one $[B]$-component, so $v\in B$. Hence $v\in conn_i\cap conn_j$, which lies in both child roots and in the root, so the occurrences are connected through the root.
  - If $v$ occurs at the root and in $D_i$: then $v\in V(C_i)\cap B = conn_i$, which is in $D_i$'s root, adjacent to the root.
  - Otherwise $v$ occurs within a single $D_i$, or only at the root, and is connected by induction. ∎

### 2.4 Lemma C (descent: a good decomposition can be re-rooted to a candidate)

Suppose $C$ is $[conn]$-connected (any two of its edges are joined by a chain of edges sharing vertices
outside $conn$), or $conn=\emptyset$, and suppose a good $D$ for $(C,conn)$ exists. Then there is a good $D'$
whose root bag $B'$ and cover $\lambda'$ satisfy $conn\subseteq B'\subseteq B(\lambda')\cap(W\cup conn)$ and
$B'\cap W\ne\emptyset$, and every bag of $D'$ lies inside $V(C)$.

*Proof.*
1. Intersect every bag of $D$ with $V(C)$. Coverage of $C$ survives because edges of $C$ lie in $V(C)$. Connectedness survives because occurrence sets only shrink to $\emptyset$ or stay as they were. Guards survive because bags only shrink. And $conn\subseteq V(C)$ stays in the root.
2. If $conn=\emptyset$, re-root at any node with a non-empty bag (one exists since $C\neq\emptyset$). Then $B'\cap W = B'\ne\emptyset$, and we are done.
3. Otherwise, if the root bag $B_r$ meets $W$ we are done, because $B_r\subseteq B(\lambda_r)$ and $B_r\subseteq V(C)$. Otherwise $B_r\subseteq conn$, and with $conn\subseteq B_r$ we get $B_r = conn$.
   - Every $e\in C$ has a vertex in $W$: if $e \subseteq conn$ then $C$ would not be $[conn]$-connected, unless $|C|=1$ with $e\subseteq conn$. That is impossible, since then $W=\emptyset$ while $C$ is a component, which by definition has a vertex outside the separator.
   - So no $e\in C$ lies inside $B_r$, and each is covered in some child subtree.
   - Two edges sharing a vertex $w\in W$ are covered in the same child subtree. Otherwise $w$ occurs in two child subtrees, so (connectedness) $w\in B_r = conn$, contradicting $w \in W$. Since $C$ is linked through $W$-vertices, all of $C$ is covered inside one child subtree $T_c$.
   - Every $v\in conn$ lies in some edge of $C$, hence occurs in $T_c$ and at $r$, hence in $B_c$.
   - So $T_c$ rooted at $c$ is good for $(C,conn)$ and has smaller height. Repeat; the process stops because the height decreases. ∎

### 2.4′ Lemma C′ (gap found in S7 review; arbitrary top-level `conn`)

Lemma C needs three hypotheses: $C$ is $[conn]$-connected, $conn\subseteq V(C)$, and no edge of $C$ lies inside $conn$. The recursion only creates states that satisfy them, because every child is a $[B]$-component, and so does the top-level call with $conn = \emptyset$. A caller of the public `decompose` may, however, pass any $(C_0, conn)$.

**Counterexample (Agent C, pinned by `test_conn_root_extension_is_needed`).** Take the path $e_1=\{a,b\}$, $e_2=\{b,c\}$, $e_3=\{c,d\}$, cover $C=\{e_1,e_3\}$, set $conn=\{b,c\}$ and $k=1$. The only guard covering $conn$ is $e_2$, and the only bag allowed by §2.1 is $\{b,c\}$, which does not meet $W=\{a,d\}$. So §2.1 has no candidate. Yet the root $(\{b,c\},\{e_2\})$ with children $\{a,b\}/\{e_1\}$ and $\{c,d\}/\{e_3\}$ is good.

**Repair.** At the top-level state only, and only when one of the three hypotheses fails, the search additionally tries the candidate $B = conn$ with some guard set $\lambda$, $|\lambda|\le k$, $conn\subseteq B(\lambda)$.

**Lemma C′.** With this extra candidate, the search is sound, complete and terminating for every top-level $(C_0, conn)$.

*Proof.*
- **Soundness:** Lemma B never uses $B\cap W\neq\emptyset$.
- **Completeness:** let $D$ be good. Restrict all bags to $V(C_0)\cup conn$; the argument of Lemma C step 1 still applies. If the root bag meets $W$, it is a regular candidate. Otherwise it equals $conn$, which is the extra candidate. Its children are the $[conn]$-components $C_i$, and the argument of Lemma D, which uses only connectedness of $D$, gives a good decomposition for each $(C_i, conn_i)$. Those states are components, so Lemma C/D and Theorem E apply below them.
- **Termination:** a child of the extra candidate has fewer edges, unless $C_0$ is a single $[conn]$-component with no inside edges, which leaves $conn
ot\subseteq V(C_0)$. In that case the child state is $(C_0, V(C_0)\cap conn)$, which is no longer the top-level state and satisfies all three hypotheses, so no extra candidate is generated again. ∎

The update pipeline itself only passes the top-level call $(\mathcal{E},\emptyset)$, or components with $conn = V(c)\cap B_{parent}$. Those satisfy Lemma C's hypotheses, so the extension is about the soundness of the general API, not of the paper's algorithm.

### 2.5 Lemma D (completeness of one step)

Let $D$ be as produced by Lemma C, with root $r$, and let $(C_i, conn_i)$ be the states produced from
$(\lambda_r, B_r)$. Then every $(C_i, conn_i)$ has a good decomposition, and every $C_i$ is $[conn_i]$-connected.

*Proof.* $C_i$ is a $[B_r]$-component, so its edges are linked through vertices outside $B_r$, hence outside $conn_i$. That gives $[conn_i]$-connectedness.
- No edge of $C_i$ is covered at $r$, because it has a vertex outside $B_r$.
- Two edges of $C_i$ sharing $w\notin B_r$ are covered in the same child subtree, by the argument of Lemma C step 3. So all of $C_i$ is covered in one child subtree $T_{c}$.
- For $v\in conn_i = V(C_i)\cap B_r$: $v$ occurs in $T_c$ (via an edge of $C_i$) and at $r$, so $v\in B_{c}$.
- Hence $T_c$ rooted at $c$ is good for $(C_i, conn_i)$. Several components may use the same $T_c$; each gets its own copy. ∎

### 2.6 Theorem E (EXACT search is sound and complete)

$S(\mathcal{E},\emptyset)$ succeeds **iff** a constrained GHD of width $\le k$ exists, and every output is one.

*Proof.* Soundness is Lemma B. For completeness, use induction on $|W|$ (well-founded by Lemma A).
- By Lemma C (applicable at the top level because $conn = \emptyset$, and at inner states by Lemma D's connectedness claim; for an arbitrary top-level $conn$ by Lemma C′), some candidate $(\lambda, B)$ enumerated by the search is the root of a good decomposition.
- By Lemma D, every child state of that candidate has a good decomposition.
- By induction, every recursive call succeeds.
- Because the search tries all candidates, it finds this one or an earlier successful one. ∎

**Corollaries for the implementation.**
- **Memoisation.** The outcome of $S(C,conn)$ depends only on $(C, conn)$, given fixed $H$, $K$ and $k$. Caching *failures* is therefore sound, and that is what makes `PROVEN_NO` trustworthy.
- **HEURISTIC mode** ($B = B(\lambda)\cap(W\cup conn)$ only) is **sound** by Lemma B, which holds for any choice of $B$. It is **not complete**: Lemma C's $B_r$ need not be maximal. This is the gap between ghw and hw.
- **Scene hints.** Trying scene candidates first only reorders the enumeration, so the EXACT verdict is unchanged (A19).

### 2.7 Lemma F (outputs are in replay normal form)

Every output of the search passes `check_normal_form`, with the components of each node matched to its children.

*Proof.* At a node with bag $B$ handling $C$, the children correspond one-to-one to the $[B]$-components $C_i$.
- **Matching.** The child root bag $B_i$ satisfies $B_i\cap W_i\ne\emptyset$ with $W_i = V(C_i)\setminus B$, so $(V(C_i)\setminus B)\cap B_i\neq\emptyset$. This is the line-16 matching rule.
- **Uniqueness of the match.** $B_i\subseteq V(C_i)$, and for $j\neq i$ we have $V(C_j)\cap V(C_i)\subseteq B$, so $(V(C_j)\setminus B)\cap B_i=\emptyset$.
- **Coverage.** Every edge of $C_i$ is covered in $D_i$ (Lemma B). ∎

So the decomposer's outputs satisfy invariant I3 by construction. This is what allows them to be fed to scene creation in later updates.

---

## 3. Paper results and the exact property each module must preserve

| Result | Property preserved | Where enforced |
|---|---|---|
| Lemma 4.2 | outer trees are kept with identical bags and covers | `constraints.gluing`, `update` (I4) |
| Lemma 4.4 | Algorithm 2's output equals the unique minimum δ-mutable subtree (EDGEWISE) | S9 differential test against `oracle.brute_mutable` |
| Theorem 4.5 | gluing a constraint-satisfying $\mathcal{D}^*$ yields a GHD of $\delta(H)$ of width $\le k$ | `glue` refuses unsatisfied constraints; validator after gluing |
| Prop 5.3 | scene creation is $O(N^3)$ | measured in S11 |
| Thm 3.6 | no polynomial update bound is claimed | documentation; `NOT_FOUND` vs `PROVEN_NO` |

---

## 4. Scope of Theorem 4.5: it holds for the six elementary classes, not for arbitrary δ (A26)

**The gap.** The coverage part (E) of Theorem 4.5's proof claims that an edge of $\delta(H)$ that does not lie inside $\delta(H)^*$ "is in H", meaning unchanged, so an outer node covers it. That is false when an edge changes by **existing** vertices only. Counterexample (verified, `test_thm45_fails_for_a_general_modification`): $H=\{e_1{:}ab,\ e_2{:}bc\}$, tree $u_1(ab)-u_2(bc)$, δ turns $e_1$ into $\{a,b,c\}$. With $X = B(T\setminus\{u_2\}) = \{a,b\}$ both conditions of Def 4.1 hold, and Algorithm 2 returns $T^*=\{u_2\}$. But $\delta(H)^*$ only contains $e_1'\cap\{b,c\}$, and after gluing no bag contains $\{a,b,c\}$. This δ is reachable by composing two elementary modifications: AddVar(z into $e_1$), then AddEq({z,c} → c).

**What the proof needs.** Call it condition (iii): every edge $e'$ of $\delta(H)$ that is new, or whose vertex set differs from its preimage, satisfies $e'\subseteq V^* = \delta(B(T^*))\cup V_{new}$. Given (iii), part (E) goes through:
- new or changed edges lie in $\delta(H)^*$ and are covered by $\mathcal{D}^*$;
- an unchanged edge $e$ is covered in the old GHD at some node $x$; if $x\in T^*$ then $e\subseteq B(T^*)$ and $e$ lies in $\delta(H)^*$; otherwise $x$ belongs to an outer tree, which is re-attached.

Parts (W), (C) and (G) of the proof do not use the edge structure and are unchanged.

**Lemma G.** For each of the six elementary classes, conditions (i) and (ii) of Def 4.1 imply (iii).

*Proof.* Write $X = B(T\setminus T^*)$. Every old vertex lies in some bag, so an old vertex not in $X$ is in $B(T^*)$. Let $e'$ be new or changed, with preimage $e$ if it exists, and let $x$ be a node covering $e$ in the old GHD.
- **AddVar($w$, E′):** $e' = e\cup\{w\}$ with $w$ new. By (ii) no vertex of $e'$ lies in $X$, so the old part $e \subseteq B(T^*)$ and $w\in V_{new}$.
- **DelVar($v$):** $e' = e\setminus\{v\}$. If $x$ were outside $T^*$, then $v\in B_x\subseteq X$ and $e\cap X \ni v \notin e'\cap X$, contradicting (i). So $x\in T^*$ and $e'\subseteq e\subseteq B(T^*)$, while $v\notin V(\delta(H))$ never mattered.
- **AddConstr($f$):** EDGEWISE (i) gives $f\cap X=\emptyset$. Its old vertices lie in $B(T^*)$, and its other vertices are new.
- **DelConstr:** no edge is new or changed.
- **AddEq($U\to w$):** $e' = (e\setminus U)\cup\{w\}$, with $e\cap U \neq\emptyset$ and $e'\neq e$.
  - If $w$ is new: (ii) gives $e'\cap X=\emptyset$.
  - If $w\in U$: some $u\in (e\cap U)\setminus\{w\}$ exists, since otherwise $e'=e$. That $u$ disappears, so if $u\in X$ then $e\cap X\neq e'\cap X$, contradicting (i). Hence $u\notin X$, so $x\notin$ the outer trees (as $u \in B_x$), so $x\in T^*$ and $e\setminus U\subseteq B(T^*)$. Finally, if $w\in X$ and $w\notin e$, then $w\in e'\cap X\setminus e$, contradicting (i). So $w\notin X$, or $w\in e\subseteq B(T^*)$, and in either case $w\in B(T^*)$.
- **DelEq($w\to$ parts):** a changed edge contains a new part, unless it only lost $w$. That cannot happen, since every incident edge receives at least one part. By (ii) $e'\cap X=\emptyset$, so the old vertices of $e'$ lie in $B(T^*)$ and the parts are new or equal to $w$. If $w$ is kept, then $w\notin X$ because $w\in e'$, so $w\in B(T^*)$. ∎

**Consequence for the implementation.** For the six classes, Theorem 4.5 and the whole §4 framework apply as stated. For any other δ (a `ModificationSequence`, a custom function), the update checks (iii) after Algorithm 2. If it fails, the update uses $T^* :=$ the whole tree. That is always valid: $\delta(H)^*=\delta(H)$ with no constraints, at the price of no reuse. Ledger L-A26.

---

## 5. Scene-creation facts observed in S11 (A27)

- **σ is not always a function in the sense of Def 5.1.** Alg 3 line 13 records $H'\mapsto n$, and lines 17–18 can record the same edge set at a child. That happens when no edge of $H'$ lies inside $\delta(B_n)$, so the single component is $H'$ itself. Reading: the deeper (child) entry wins, and the replacement is recorded in `SceneMapping.overwritten`. Example: $H=\{e_0{:}be, e_1{:}af, e_2{:}b\}$, root $\{a,f\}$ with child $\{b,e\}$, DelConstr($e_1$). Observed 16 times in 1,469 random runs.
- **Root scene with $T^*=\emptyset$** (A12) is keyed by all of $E(\delta(H))$, including fresh edges that lie in no old bag. In DecompUpdate (Alg 5 lines 7–10) such an edge forms its own $[B_{root}]$-component with connection $\emptyset$. It has no scene, so the decomposer handles it and the result stays valid. To be pinned in S12.
- **Alg 4 line 15 never failed** when reached from Alg 3 in 1,469 random runs. Unproved observation.

---

## 6. Validity of DecompUpdate's assembly (S12)

The state of DecompUpdate is $(H', conn)$: an edge set with its connection to the parent separator. A reused scene node $u$ must pass these checks:
- **guard** (L-A16): $\delta(B_u)\subseteq B(\delta(\lambda_u))$;
- **interface** (L-A21): $conn\subseteq$ bag;
- **progress:** the bag meets $V(H')\setminus conn$;
- $|\delta(\lambda_u)|\le k$.

The children are the [bag]-components $c$ of $H'$ with $conn_c = V(c)\cap$ bag.

**Lemma H.** With `restrict_reused_bags = True` (bag $:=\delta(B_u)\cap(V(H')\cup conn)$), every FOUND result of DecompUpdate for $(H', conn)$ is good for $(H', conn)$, with all bags inside $V(H')\cup conn$. Every call terminates.

*Proof.* Induction on $|V(H')\setminus conn|$.
- **Fragments from the decomposer** are good, with bags inside $V(c)\cup conn_c$, by Lemma B (and Lemma C′ for the top call).
- **A reused node** has a bag $B$ with $conn\subseteq B\subseteq V(H')\cup conn$, $B\subseteq B(\lambda)$ and $|\lambda|\le k$, and its children are good for their component states by induction. This is exactly the situation of Lemma B, whose proof only uses these properties.
- **Termination** follows from the progress check, as in Lemma A.

**Under the literal default** (`restrict_reused_bags = False`), a reused bag may contain vertices outside $V(H')\cup conn$, and Lemma B's connectedness argument no longer applies. Validity is then **checked** by the validator on every output, not proved.

**Observations:**
- With all default checks on, **no invalid output occurred** in the S12 random runs: 1,800 differential cases × 4 strategy variants, 3,149 chained steps, and 3,000 further updates.
- **Without the interface check** (A21), literal Algorithm 5 produced invalid outputs in 37 of 3,000 updates, including a wrong "yes" (`test_a21_interface_check_is_required_by_the_paper_algorithm`).

**Authority of the verdict.** At the top level, a failure always ends in the decomposer on $(E(\delta(H)),\emptyset)$: either the root has no usable scene, or the A18 fallback is taken. So `PROVEN_NO` is the verdict of an EXACT search over all of $\delta(H)$ (invariant I10, Theorem E). Scene hints do not change it.

**Normal form of outputs (A29).** Algorithm 5's outputs were in replay normal form in every random case, but this is unproved. Outputs of the DelVar rule are not always in normal form, which is why `delvar_fast_path=False` exists.

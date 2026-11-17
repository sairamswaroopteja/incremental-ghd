"""S0 smoke tests: the interface surface exists, the shared utilities work, and the paper
fixtures are faithful transcriptions. These checks deliberately use plain Python only, so they
do not depend on any module that is still a stub."""

from __future__ import annotations

import importlib

import pytest

from ighd.common import (
    PAPER_DEFAULT, Budget, BudgetExhausted, InducedComparison, SearchStatus, UpdateStatus, UpSceneKey,
)
from tests.fixtures import expected, paper

# ------------------------------------------------------------------- interface surface
PUBLIC_API = {
    "ighd.common": ["Budget", "Semantics", "PAPER_DEFAULT", "SearchStatus", "UpdateStatus", "Minimality",
                    "DecomposerMode", "todo"],
    "ighd.hypergraph": ["Hypergraph", "induced_equal", "induced_diff", "parse_hyperbench", "to_hyperbench"],
    "ighd.modifications": ["AddVar", "DelVar", "AddConstr", "DelConstr", "AddEq", "DelEq",
                           "ModificationResult", "ModificationSequence", "compose"],
    "ighd.ghd": ["GHD", "Node", "validate", "width", "check_normal_form", "ValidationReport"],
    "ighd.oracle": ["exact_ghw", "edge_cover_number", "all_mutable_subtrees"],
    "ighd.static": ["components", "inside_edges", "connection", "TopDownDecomposer", "DecompositionTask",
                    "ghw_by_search"],
    "ighd.mutable": ["mutable_conditions", "minimal_mutable_subtree", "Alg2Step"],
    "ighd.constraints": ["redecomposition_target", "bag_constraints", "glue", "BagConstraint"],
    "ighd.scenes": ["SceneMapping", "SceneKind", "scene_create"],
    "ighd.update": ["ghd_update", "UpdateResult", "UpdateTrace", "Strategy"],
}


@pytest.mark.parametrize("module,names", sorted(PUBLIC_API.items()))
def test_public_api_importable(module: str, names: list[str]) -> None:
    mod = importlib.import_module(module)
    missing = [n for n in names if not hasattr(mod, n)]
    assert not missing, f"{module} lacks {missing}"


def test_no_submodule_is_shadowed_by_a_reexport() -> None:
    """``import ighd.x.y as m`` must give a module: no package re-exports a name equal to one of
    its submodules (found in S0: validate/exact_ghw/components/ghd_update clashed)."""
    import pkgutil
    import types
    for pkg_name in PUBLIC_API:
        pkg = importlib.import_module(pkg_name)
        for info in pkgutil.iter_modules(pkg.__path__):
            attr = getattr(pkg, info.name, None)
            assert attr is None or isinstance(attr, types.ModuleType), f"{pkg_name}.{info.name} is shadowed"


def test_stub_fails_loudly_with_stage() -> None:
    """The stub marker names its stage. Tests the marker itself, so it does not go stale as
    stages land (it used to call the S6 stub, which S6 then implemented)."""
    from ighd.common import todo
    with pytest.raises(NotImplementedError, match="stage S99"):
        todo("S99")


def test_independence_rule_imports() -> None:
    """Validator and oracle must not import the modules they judge (IMPLEMENTATION_PLAN §A.1.3)."""
    judges = ["ighd.ghd.validation", "ighd.oracle.edge_cover", "ighd.oracle.ghw_dp", "ighd.oracle.brute_mutable"]
    forbidden = ("ighd.static", "ighd.update", "ighd.scenes", "ighd.constraints", "ighd.mutable")
    import ast
    for mod in map(importlib.import_module, judges):
        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module]
        imported += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        bad = [m for m in imported if m.startswith(forbidden)]
        assert not bad, f"{mod.__name__} imports {bad}"


# ------------------------------------------------------------------- common utilities
def test_semantics_defaults_match_ledger() -> None:
    s = PAPER_DEFAULT
    assert s.induced_comparison is InducedComparison.EDGEWISE      # A2
    assert s.inside_edges_form_components is False                   # A3
    assert s.scene_guard_check is True                               # A16
    assert s.up_scene_key is UpSceneKey.COVERED_EDGES                # A17
    assert s.strict_child_matching is True                           # A23
    assert s.scene_interface_check is True                           # A21
    assert s.restrict_reused_bags is False                           # A28 (literal Alg 5)


def test_result_enums_distinguish_proof_from_failure() -> None:
    assert SearchStatus.PROVEN_NO is not SearchStatus.NOT_FOUND
    assert {s.value for s in UpdateStatus} == {"updated", "proven_no", "not_found"}


def test_budget_expansions() -> None:
    b = Budget(max_expansions=3).start()
    b.charge(3)
    with pytest.raises(BudgetExhausted):
        b.charge()


def test_budget_unlimited() -> None:
    b = Budget()
    assert b.unlimited
    b.charge(10_000)
    assert b.expansions == 10_000


# ------------------------------------------------------------------- fixture faithfulness
HYPERGRAPHS = {"H_P": paper.H_P, "H_PP": paper.H_PP, "H_P2": paper.H_P2, "H_P3": paper.H_P3}
SPECS = {
    "G_PRIME_SPEC": (paper.G_PRIME_SPEC, paper.H_PP),
    "G2_SPEC": (paper.G2_SPEC, paper.H_P2),
    "JOIN_TREE_HP_SPEC": (paper.JOIN_TREE_HP_SPEC, paper.H_P),
    "S_SPEC": (paper.S_SPEC, paper.H_P3),
}


@pytest.mark.parametrize("name", sorted(HYPERGRAPHS))
def test_hypergraph_fixture_edges_nonempty(name: str) -> None:
    assert all(HYPERGRAPHS[name].values()), name


def test_example_3_5_relations() -> None:
    """AddVar(h into w2, w5): H_P -> H_P'; AddConstr(w7): H_P' -> H_P2; AddEq(b into g): H_P' -> H_P3."""
    addvar = {n: (vs | {"h"} if n in {"w2", "w5"} else vs) for n, vs in paper.H_P.items()}
    assert addvar == paper.H_PP
    assert {n: vs for n, vs in paper.H_P2.items() if n != "w7"} == paper.H_PP
    merged = {n: frozenset("g" if v == "b" else v for v in vs) for n, vs in paper.H_PP.items()}
    assert merged == paper.H_P3


def test_example_2_1_solution_spells_words() -> None:
    assert set(paper.SCOPES_PP) == set(paper.H_PP)
    for name, scope in paper.SCOPES_PP.items():
        assert frozenset(scope) == paper.H_PP[name]
        word = "".join(paper.SOLUTION_EX21[v] for v in scope)
        assert word in paper.WORDS_EX21, (name, word)


def _tree_edges(spec: dict) -> list[tuple[str, str]]:
    return [(p, c) for p, cs in spec["children"].items() for c in cs]


@pytest.mark.parametrize("name", sorted(SPECS))
def test_spec_is_a_rooted_tree(name: str) -> None:
    spec, _ = SPECS[name]
    labels = set(spec["nodes"])
    edges = _tree_edges(spec)
    kids = [c for _, c in edges]
    assert len(kids) == len(set(kids)), "a node has two parents"
    assert set(kids) == labels - {spec["root"]}
    assert len(edges) == len(labels) - 1
    seen, stack = set(), [spec["root"]]
    while stack:
        x = stack.pop()
        seen.add(x)
        stack.extend(spec["children"].get(x, []))
    assert seen == labels


@pytest.mark.parametrize("name", sorted(SPECS))
def test_spec_is_a_ghd_transcription_check(name: str) -> None:
    """Plain-Python transcription check of conditions (1)-(3). NOT the validator (stage S4),
    which is written independently; this only guards against typos in the fixtures."""
    spec, h = SPECS[name]
    bags = {u: frozenset(b) for u, (b, _) in spec["nodes"].items()}
    covers = {u: tuple(c) for u, (_, c) in spec["nodes"].items()}
    for e, vs in h.items():                                   # (1) edge coverage
        assert any(vs <= b for b in bags.values()), (name, e)
    adj: dict[str, set[str]] = {u: set() for u in bags}
    for p, c in _tree_edges(spec):
        adj[p].add(c)
        adj[c].add(p)
    for v in frozenset().union(*h.values()):                  # (2) connectedness
        occ = {u for u, b in bags.items() if v in b}
        start = next(iter(occ))
        seen, stack = {start}, [start]
        while stack:
            for y in adj[stack.pop()] & occ - seen:
                seen.add(y)
                stack.append(y)
        assert seen == occ, (name, v)
    for u, b in bags.items():                                 # (3) guards
        assert all(e in h for e in covers[u]), (name, u)
        assert b <= frozenset().union(*(h[e] for e in covers[u])), (name, u)


def test_expected_width_of_fixture_specs() -> None:
    assert max(len(c) for _, c in paper.G_PRIME_SPEC["nodes"].values()) == 2
    assert max(len(c) for _, c in paper.JOIN_TREE_HP_SPEC["nodes"].values()) == expected.GHW["H_P"]


def test_expected_tables_reference_known_labels() -> None:
    for case_id, _h, spec, (cls, _kw), t_star, _prov in expected.T_STAR_CASES:
        assert t_star <= set(spec["nodes"]), case_id
        assert hasattr(importlib.import_module("ighd.modifications"), cls), case_id
    for key, (label, kind) in expected.EX52_SIGMA_PSEUDOCODE.items():
        assert label in paper.G2_SPEC["nodes"] and kind in {"in", "out"}
        assert key <= frozenset(paper.H_PP)

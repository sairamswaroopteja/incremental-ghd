"""Cross-module check (main agent, W2 review): every expected minimal delta-mutable subtree in
tests/fixtures/expected.py is reproduced by applying the REAL modification (S2) and asking the
independent brute-force oracle (S5). Pins three independently written things at once: the
modification ops, the Def 4.1 oracle, and the hand-derived expectations (paper Ex. 4.3; guide §8).
Also records each case's ghw before/after, which S12 must reproduce (UPDATED vs PROVEN_NO)."""

from __future__ import annotations

import pytest

import ighd.modifications as mods
from ighd.common.config import InducedComparison, Semantics
from ighd.ghd import GHD, validate
from ighd.hypergraph import Hypergraph
from ighd.oracle import all_mutable_subtrees, exact_ghw
from tests.fixtures import expected

# case id -> (ghw before, ghw after); the input GHDs all have width == ghw before (minimal).
GHW_BEFORE_AFTER = {
    "ex43_delconstr": (2, 2), "addconstr_w7": (2, 2), "addvar_m": (2, 2), "addeq_bg": (2, 2),
    "deleq_g": (2, 2), "addvar_h_jointree": (1, 2), "delvar_h": (2, 1),
}


@pytest.mark.parametrize("case", expected.T_STAR_CASES, ids=[c[0] for c in expected.T_STAR_CASES])
@pytest.mark.parametrize("mode", list(InducedComparison))
def test_expected_minimum_is_unique_and_matches(case, mode) -> None:
    case_id, h, spec, (cls, kwargs), want, _prov = case
    hyper, ghd = Hypergraph(h), GHD.from_spec(spec)
    change = getattr(mods, cls)(**kwargs).apply(hyper)
    subs = all_mutable_subtrees(change, ghd, Semantics(induced_comparison=mode))
    size = min(map(len, subs))
    minima = [frozenset(ghd.node(i).label for i in s) for s in subs if len(s) == size]
    assert minima == [want], (case_id, mode, minima)


@pytest.mark.parametrize("case", expected.T_STAR_CASES, ids=[c[0] for c in expected.T_STAR_CASES])
def test_inputs_are_minimal_width_ghds_and_ghw_change(case) -> None:
    case_id, h, spec, (cls, kwargs), _want, _prov = case
    hyper, ghd = Hypergraph(h), GHD.from_spec(spec)
    report = validate(hyper, ghd)
    assert report.ok, report.violations
    before, after = GHW_BEFORE_AFTER[case_id]
    assert exact_ghw(hyper)[0] == before == report.width   # SearchUpdateGHD precondition holds
    assert exact_ghw(getattr(mods, cls)(**kwargs).apply(hyper).new)[0] == after

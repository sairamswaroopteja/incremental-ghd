"""The online, query-based system (ighd.online): session semantics and the command interface.

Session (random streams, every step checked against the exact oracle):
  * after every step the current GHD validates against the current hypergraph, width = k;
  * with tightening on (default) and no time limit, k = ghw exactly (oracle) and exact is True;
  * with tightening off, k >= ghw, and exact is claimed only when it is true;
  * a time limit never yields a PROVEN_NO answer or an 'exact' claim it cannot back;
  * invalid modifications raise and leave the state unchanged; undo restores the previous state.
Shell: every command form parses to the intended modification; scripts run end to end.
"""

from __future__ import annotations

import random

import pytest

from ighd.common.errors import IGHDError
from ighd.ghd import validate
from ighd.hypergraph import Hypergraph
from ighd.modifications import AddConstr, AddEq, AddVar, DelConstr, DelEq, DelVar
from ighd.online import OnlineSession, Shell
from ighd.online.cli import main, parse_modification, TOKEN
from ighd.oracle import exact_ghw
from ighd.testing import KINDS, random_hypergraph, random_modification
from ighd.common.errors import InvalidModificationError
from ighd.update import Strategy

fs = frozenset


def run_streams(seed: int, streams: int, steps: int, **kw) -> dict:
    rng = random.Random(seed)
    st = {"steps": 0, "rises": 0, "drops": 0, "proven_no": 0}
    for _ in range(streams):
        h = random_hypergraph(rng)
        s = OnlineSession(**kw)
        s.build(h)
        assert s.exact and s.k == exact_ghw(h)[0]
        for _ in range(steps):
            mod = random_modification(rng, s.h, rng.choice(KINDS))
            if mod is None:
                continue
            try:
                new = mod.apply(s.h).new
            except InvalidModificationError:
                continue
            if not new.edge_names or len(new.vertices) > 14:
                break
            before, truth = exact_ghw(s.h)[0], exact_ghw(new)[0]
            k_before = s.k
            rep = s.apply(mod)
            ctx = (seed, dict(new.edges), mod, rep)
            v = validate(s.h, s.ghd)
            assert v.ok and v.width == s.k, ctx
            assert s.k >= truth, ctx                                    # always a valid upper bound
            assert (rep.status == "proven_no") == (truth > k_before), ctx   # exact update answer
            if kw.get("tighten", True):
                assert s.exact and s.k == truth, ctx
            if s.exact:
                assert s.k == truth, ctx                                # 'exact' is never a guess
            st["steps"] += 1
            st["proven_no"] += rep.status == "proven_no"
            st["rises"] += truth > before
            st["drops"] += truth < before
    return st


def test_streams_track_ghw_exactly() -> None:
    st = run_streams(seed=11, streams=40, steps=10)
    print(st)
    assert st["steps"] >= 250 and st["rises"] >= 5 and st["drops"] >= 5


@pytest.mark.parametrize("strategy", [Strategy.THEOREM45, Strategy.RECOMPUTE])
def test_streams_other_strategies(strategy) -> None:
    st = run_streams(seed=12, streams=15, steps=8, strategy=strategy)
    assert st["steps"] >= 80


def test_streams_without_tightening_give_upper_bounds() -> None:
    st = run_streams(seed=13, streams=30, steps=10, tighten=False)
    assert st["steps"] >= 200


@pytest.mark.slow
def test_streams_track_ghw_exactly_large() -> None:
    st = run_streams(seed=14, streams=400, steps=15)
    print(st)
    assert st["steps"] >= 3000


def _cycle6() -> Hypergraph:
    return Hypergraph({f"e{i}": (a, b) for i, (a, b) in
                       enumerate(zip("abcdef", "bcdefa"), 1)})


def test_invalid_modification_changes_nothing_and_undo_restores() -> None:
    s = OnlineSession()
    s.build(_cycle6())
    h, g, k = s.h, s.ghd, s.k
    with pytest.raises(IGHDError):
        s.apply(AddVar("z", fs({"nope"})))
    assert (s.h, s.ghd, s.k) == (h, g, k)
    s.apply(AddConstr("c1", fs("ad")))
    assert s.h != h
    assert s.undo() and (s.h, s.ghd, s.k) == (h, g, k)


def test_rise_and_drop_are_reported() -> None:
    s = OnlineSession()
    s.build(Hypergraph({"e1": "ab", "e2": "bc", "e3": "cd"}))
    assert s.k == 1
    r = s.apply(AddConstr("e4", fs("da")))                      # closes a 4-cycle
    assert r.status == "proven_no" and s.k == 2 and s.exact
    r = s.apply(AddConstr("big", fs("abcd")))                   # one edge covers everything
    assert r.status == "updated" and s.k == 1 and s.exact       # tightening found width 1
    assert any("ghw dropped" in n for n in r.notes)


def test_time_limit_never_claims_a_proof() -> None:
    s = OnlineSession(time_limit_s=1e-9)
    s.build(Hypergraph({"e1": "ab", "e2": "bc"}))     # build may itself time out
    for mod in (AddConstr("e3", fs("ca")), AddVar("x", fs({"e1"})), DelConstr("e1")):
        if s.ghd is None:
            assert not s.exact
            with pytest.raises(IGHDError, match="rebuild"):
                s.apply(mod)
            break
        rep = s.apply(mod)
        assert rep.status != "proven_no"
        if s.ghd is not None:
            assert validate(s.h, s.ghd).ok


# ------------------------------------------------------------------------------ command parsing
def toks(text: str) -> list[str]:
    return TOKEN.findall(text)


def test_parse_every_modification() -> None:
    assert parse_modification("addvar", toks("x e1 e2")) == AddVar("x", fs({"e1", "e2"}))
    assert parse_modification("delvar", toks("x")) == DelVar("x")
    assert parse_modification("addconstr", toks("f a, b, c")) == AddConstr("f", fs("abc"))
    assert parse_modification("addconstr", toks("f (a,b)")) == AddConstr("f", fs("ab"))
    assert parse_modification("delconstr", toks("e3")) == DelConstr("e3")
    assert parse_modification("addeq", toks("b c -> b")) == AddEq(fs("bc"), "b")
    assert parse_modification("addeq", toks("b,c->z")) == AddEq(fs("bc"), "z")
    assert parse_modification("deleq", toks("b : b = e1 e2 ; c = e3")) == \
        DelEq("b", {"b": fs({"e1", "e2"}), "c": fs({"e3"})})
    for cmd, bad in [("addvar", "x"), ("delvar", "x y"), ("addeq", "a b"), ("addeq", "a -> b c"),
                     ("deleq", "b b = e1"), ("deleq", "b : b e1"), ("deleq", "b : p = e1 ; p = e2")]:
        with pytest.raises(ValueError):
            parse_modification(cmd, toks(bad))


def test_shell_end_to_end(tmp_path) -> None:
    sh = Shell()
    assert "error" in sh.execute("ghw")
    sh.execute("edge e1 a b")
    sh.execute("e2(b,c), e3(c,d).")
    out = sh.execute("addconstr e4 d a")            # auto-start, then the modification
    assert "initial hypergraph" in out and "NO GHD of width 1" in out
    assert "ghw = 2  (proven" in sh.execute("ghw")
    assert "valid GHD: True" in sh.execute("check")
    assert "error" in sh.execute("addvar z e9") and sh.session.k == 2
    assert "undone" in sh.execute("undo") and sh.session.k == 1
    assert "error" in sh.execute("edge e9 x y")     # initial hypergraph is fixed after start
    p = tmp_path / "dir with space" / "h.hg"           # Windows paths: backslashes and spaces
    p.parent.mkdir()
    assert "wrote" in sh.execute(f"save {p}")
    assert p.is_file()                                  # written exactly where asked
    sh2 = Shell()
    sh2.execute(f'load "{p}"')
    sh2.execute("start")
    assert sh2.session.h.edges == sh.session.h.edges
    assert "unknown command" in sh.execute("frobnicate")
    assert "strategy = theorem45" in sh.execute("strategy theorem45")
    assert "timeout = 2.5" in sh.execute("timeout 2.5")


def test_main_runs_a_script(tmp_path, capsys) -> None:
    script = tmp_path / "s.txt"
    script.write_text("edge e1 a b\nedge e2 b c\nstart\naddconstr e3 c a\nghw\n", encoding="utf-8")
    assert main(["--script", str(script), "--oracle", "--no-interactive"]) == 0
    out = capsys.readouterr().out
    assert "ghw = 2  (proven by exact search)" in out and "(agrees)" in out

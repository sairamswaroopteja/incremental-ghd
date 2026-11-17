"""S11: the SceneMapping container (Def 5.1; lookup semantics of Alg 5, p. 17)."""

from __future__ import annotations

from ighd.scenes import SceneEntry, SceneKind, SceneMapping

fs = frozenset


def test_in_scene_is_consumed_exactly_once() -> None:
    m = SceneMapping()
    m.add(fs({"a", "b"}), SceneEntry(3, SceneKind.IN, "down"))
    first = m.lookup(fs({"a", "b"}))
    assert first is not None and first.node == 3 and first.consumed
    assert m.lookup(fs({"a", "b"})) is None
    assert m.lookup({"b", "a"}) is None  # any set type is accepted as a key
    assert len(m) == 1  # consumption does not remove the entry


def test_out_scene_is_repeatable() -> None:
    m = SceneMapping()
    m.add(fs({"x"}), SceneEntry(7, SceneKind.OUT, "up"))
    for _ in range(3):
        e = m.lookup(fs({"x"}))
        assert e is not None and e.node == 7 and not e.consumed


def test_unknown_key() -> None:
    m = SceneMapping()
    assert m.lookup(fs({"q"})) is None and m.peek(fs({"q"})) is None
    assert fs({"q"}) not in m and len(m) == 0


def test_peek_does_not_consume_and_sees_consumed_entries() -> None:
    m = SceneMapping()
    m.add(fs({"a"}), SceneEntry(1, SceneKind.IN, "down"))
    for _ in range(2):
        p = m.peek(fs({"a"}))
        assert p is not None and not p.consumed
    assert m.lookup(fs({"a"})) is not None
    p = m.peek(fs({"a"}))
    assert p is not None and p.consumed and p.node == 1
    assert fs({"a"}) in m


def test_overwrite_is_recorded() -> None:
    m = SceneMapping()
    first = SceneEntry(1, SceneKind.IN, "down")
    second = SceneEntry(2, SceneKind.OUT, "down")
    m.add(fs({"a", "b"}), first)
    assert m.overwritten == []
    m.add(fs({"b", "a"}), second)
    assert m.peek(fs({"a", "b"})) is second
    assert m.overwritten == [(fs({"a", "b"}), first, second)]
    assert len(m) == 1


def test_merge_carries_entries_and_overwrites() -> None:
    inner = SceneMapping()
    a1, a2 = SceneEntry(1, SceneKind.OUT, "up"), SceneEntry(2, SceneKind.OUT, "up")
    inner.add(fs({"a"}), a1)
    inner.add(fs({"a"}), a2)  # recorded inside the fragment
    outer = SceneMapping()
    b0 = SceneEntry(0, SceneKind.IN, "down")
    outer.add(fs({"a"}), b0)
    outer.merge(inner)
    assert outer.peek(fs({"a"})) is a2
    assert outer.overwritten == [(fs({"a"}), a1, a2), (fs({"a"}), b0, a2)]


def test_items_are_deterministic() -> None:
    keys = [fs({"w6"}), fs({"w2", "w4"}), fs({"w1", "w2", "w3"}), fs({"w10"}), fs({"a"})]
    m1, m2 = SceneMapping(), SceneMapping()
    for i, k in enumerate(keys):
        m1.add(k, SceneEntry(i, SceneKind.OUT, "down"))
    for i, k in reversed(list(enumerate(keys))):
        m2.add(k, SceneEntry(i, SceneKind.OUT, "down"))
    order1 = [k for k, _ in m1.items()]
    assert order1 == [k for k, _ in m2.items()]
    assert order1 == sorted(keys, key=lambda k: tuple(sorted(k)))
    assert order1[0] == fs({"a"}) and order1[1] == fs({"w1", "w2", "w3"})

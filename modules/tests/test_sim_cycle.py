"""Tests for modules/rtl_buddy/sim.py — ExpandRunsMod (spec 08a)."""

import importlib.util
from pathlib import Path

from modules.rtl_buddy.schema import KeyedValue
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_sim",
    Path(__file__).parent.parent / "rtl_buddy" / "sim.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
ExpandRunsMod = _mod.ExpandRunsMod


def _make_tb():
    return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


def _make_test(name="mytest", **overrides):
    defaults = dict(
        name=name,
        desc=f"{name} test",
        model="sandbox",
        model_path="models.yaml",
        suite_dir=Path("/design/verif"),
        reglvl=None,
        pa=None,
        pd=None,
        uvm=None,
        preproc_path=None,
        postproc_path=None,
        sweep_path=None,
        tb=_make_tb(),
        timeout=None,
    )
    defaults.update(overrides)
    return TestConfig(**defaults)


def _make_simv(key, value="/build/obj_dir/simv"):
    return KeyedValue(key, value)


# ---------------------------------------------------------------------------
# Default run_ids=[None]: single passthrough triple, key unchanged
# ---------------------------------------------------------------------------


def test_default_passthrough():
    test = _make_test()
    simv = _make_simv(test.key)
    mod = ExpandRunsMod()
    results = list(mod.run(test=test, simv=simv))
    assert len(results) == 3
    port0, val0 = results[0]
    port1, val1 = results[1]
    port2, val2 = results[2]
    assert port0 == "test"
    assert port1 == "run_id"
    assert port2 == "simv"
    assert val0.key == test.key
    assert val0 is not test
    assert val1 == KeyedValue(test.key, None)
    assert val2 == KeyedValue(test.key, simv.value)


# ---------------------------------------------------------------------------
# run_ids=[1, 2, 3]: fan-out ×3 with suffixed keys
# ---------------------------------------------------------------------------


def test_multi_run_ids():
    test = _make_test()
    simv = _make_simv(test.key, "/build/simv")
    mod = ExpandRunsMod()
    results = list(mod.run(test=test, simv=simv, run_ids=[1, 2, 3]))
    assert len(results) == 9
    for i, run_id in enumerate([1, 2, 3]):
        nk = f"{test.key}#{run_id}"
        port_t, val_t = results[i * 3 + 0]
        port_r, val_r = results[i * 3 + 1]
        port_s, val_s = results[i * 3 + 2]
        assert port_t == "test"
        assert port_r == "run_id"
        assert port_s == "simv"
        assert val_t.key == nk
        assert val_t is not test
        assert val_r == KeyedValue(nk, run_id)
        assert val_s == KeyedValue(nk, simv.value)
    # distinct replace-copies sharing pa/pd/tb by reference
    copies = [results[i * 3][1] for i in range(3)]
    assert copies[0] is not copies[1]
    assert copies[1] is not copies[2]
    assert copies[0].tb is test.tb
    assert copies[0].pa is test.pa
    assert copies[0].pd is test.pd


# ---------------------------------------------------------------------------
# run_ids=[0]: key suffixed because 0 is not None
# ---------------------------------------------------------------------------


def test_zero_run_id_is_suffixed():
    test = _make_test()
    simv = _make_simv(test.key)
    mod = ExpandRunsMod()
    results = list(mod.run(test=test, simv=simv, run_ids=[0]))
    assert len(results) == 3
    nk = f"{test.key}#0"
    port_t, val_t = results[0]
    port_r, val_r = results[1]
    port_s, val_s = results[2]
    assert val_t.key == nk
    assert val_r == KeyedValue(nk, 0)
    assert val_s.key == nk


# ---------------------------------------------------------------------------
# run_ids=[]: yields nothing
# ---------------------------------------------------------------------------


def test_empty_run_ids_yields_nothing():
    test = _make_test()
    simv = _make_simv(test.key)
    mod = ExpandRunsMod()
    results = list(mod.run(test=test, simv=simv, run_ids=[]))
    assert len(results) == 0


# ---------------------------------------------------------------------------
# Inbound test/simv not mutated; each emitted test is a fresh replace-copy
# ---------------------------------------------------------------------------


def test_inbound_not_mutated():
    test = _make_test()
    original_key = test.key
    simv = _make_simv(test.key)
    mod = ExpandRunsMod()
    results = list(mod.run(test=test, simv=simv, run_ids=[1, 2]))
    assert test.key == original_key
    copies = [results[i * 3][1] for i in range(2)]
    assert copies[0] is not test
    assert copies[1] is not test
    assert copies[0] is not copies[1]

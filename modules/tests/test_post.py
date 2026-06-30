"""Tests for modules/rtl_buddy/sim.py — RoutePostMod (spec 09a)."""

import importlib.util
from pathlib import Path

from modules.rtl_buddy.schema import Proc
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig
from modules.rtl_buddy.schema.uvm import UVMConfig

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_sim",
    Path(__file__).parent.parent / "rtl_buddy" / "sim.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RoutePostMod = _mod.RoutePostMod


def _make_tb():
    return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


def _make_test(uvm=None, name="mytest"):
    return TestConfig(
        name=name,
        desc=f"{name} test",
        model="sandbox",
        model_path="models.yaml",
        suite_dir=Path("/design/verif"),
        reglvl=None,
        pa=None,
        pd=None,
        uvm=uvm,
        preproc_path=None,
        postproc_path=None,
        sweep_path=None,
        tb=_make_tb(),
        timeout=None,
    )


def _make_proc(key):
    return Proc(key=key, rc=0, stdout_path=Path("/tmp/sim.log"), stderr_path=Path("/tmp/sim.err"))


# ---------------------------------------------------------------------------
# UVM branch: test.uvm is a UVMConfig
# ---------------------------------------------------------------------------


def test_route_post_uvm_branch():
    uvm = UVMConfig(max_warns=5, max_errors=2)
    test = _make_test(uvm=uvm)
    proc = _make_proc(test.key)
    mod = RoutePostMod()
    results = list(mod.run(test=test, proc=proc))
    assert len(results) == 2
    assert results[0] == ("uvm_test", test)
    assert results[1] == ("uvm_proc", proc)
    assert results[0][1] is test
    assert results[1][1] is proc


# ---------------------------------------------------------------------------
# Plain branch: test.uvm is None
# ---------------------------------------------------------------------------


def test_route_post_plain_branch():
    test = _make_test(uvm=None)
    proc = _make_proc(test.key)
    mod = RoutePostMod()
    results = list(mod.run(test=test, proc=proc))
    assert len(results) == 2
    assert results[0] == ("plain_test", test)
    assert results[1] == ("plain_proc", proc)
    assert results[0][1] is test
    assert results[1][1] is proc


# ---------------------------------------------------------------------------
# Zero-threshold UVMConfig still routes UVM (routes on is not None, not truthiness)
# ---------------------------------------------------------------------------


def test_route_post_zero_threshold_uvm_still_routes_uvm():
    uvm = UVMConfig(max_warns=0, max_errors=0)
    test = _make_test(uvm=uvm)
    proc = _make_proc(test.key)
    mod = RoutePostMod()
    results = list(mod.run(test=test, proc=proc))
    assert len(results) == 2
    assert results[0][0] == "uvm_test"
    assert results[1][0] == "uvm_proc"


# ---------------------------------------------------------------------------
# Identity passthrough: chosen branch carries test+proc unchanged, other emits nothing
# ---------------------------------------------------------------------------


def test_route_post_identity_passthrough_uvm():
    uvm = UVMConfig(max_warns=1, max_errors=0)
    test = _make_test(uvm=uvm)
    proc = _make_proc(test.key)
    mod = RoutePostMod()
    results = list(mod.run(test=test, proc=proc))
    ports = [r[0] for r in results]
    assert "plain_test" not in ports
    assert "plain_proc" not in ports
    assert results[0][1] is test  # same object, not a copy
    assert results[1][1] is proc


def test_route_post_identity_passthrough_plain():
    test = _make_test(uvm=None)
    proc = _make_proc(test.key)
    mod = RoutePostMod()
    results = list(mod.run(test=test, proc=proc))
    ports = [r[0] for r in results]
    assert "uvm_test" not in ports
    assert "uvm_proc" not in ports
    assert results[0][1] is test  # same object, not a copy
    assert results[1][1] is proc

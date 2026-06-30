"""Tests for modules/rtl_buddy/setup.py selection/expansion modules."""

import importlib.util
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema import SuiteConfig
from modules.rtl_buddy.schema.suite import TestbenchConfig, TestConfig

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_setup",
    Path(__file__).parent.parent / "rtl_buddy" / "setup.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RouteListModeMod = _mod.RouteListModeMod
ListTestNamesMod = _mod.ListTestNamesMod
SelectTestsMod = _mod.SelectTestsMod


def _suite_cfg(tests=None):
    return SuiteConfig(path=Path("/fake/tests.yaml"), tests=tests or {})


# ---------------------------------------------------------------------------
# RouteListModeMod
# ---------------------------------------------------------------------------


def test_route_list_mode_list_true():
    cfg = _suite_cfg({"t1": None})
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg, list=True)
    assert port == "list"
    assert result is cfg


def test_route_list_mode_list_false():
    cfg = _suite_cfg({"t1": None})
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg, list=False)
    assert port == "run"
    assert result is cfg


def test_route_list_mode_default():
    cfg = _suite_cfg({"t1": None})
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg)
    assert port == "run"
    assert result is cfg


def test_route_list_mode_empty_suite():
    cfg = _suite_cfg()
    mod = RouteListModeMod()
    port, result = mod.run(suite_cfg=cfg, list=False)
    assert port == "run"
    assert result is cfg


# ---------------------------------------------------------------------------
# ListTestNamesMod
# ---------------------------------------------------------------------------


def test_list_test_names_three_tests(capsys):
    cfg = _suite_cfg({"alpha": None, "beta": None, "gamma": None})
    mod = ListTestNamesMod()
    result = mod.run(suite_cfg=cfg)
    assert result is None
    assert capsys.readouterr().out == "alpha  beta  gamma\n"


def test_list_test_names_declaration_order(capsys):
    cfg = _suite_cfg({"zebra": None, "alpha": None})
    mod = ListTestNamesMod()
    mod.run(suite_cfg=cfg)
    assert capsys.readouterr().out == "zebra  alpha\n"


def test_list_test_names_single(capsys):
    cfg = _suite_cfg({"only": None})
    mod = ListTestNamesMod()
    mod.run(suite_cfg=cfg)
    assert capsys.readouterr().out == "only\n"


def test_list_test_names_empty(capsys):
    cfg = _suite_cfg()
    mod = ListTestNamesMod()
    mod.run(suite_cfg=cfg)
    assert capsys.readouterr().out == "\n"


# ---------------------------------------------------------------------------
# SelectTestsMod helpers
# ---------------------------------------------------------------------------


def _make_tb(**overrides):
    defaults = dict(name="tb_top", filelist=["rtl/top.sv"])
    defaults.update(overrides)
    return TestbenchConfig(**defaults)


def _make_test(name, **overrides):
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


def _suite3():
    t1 = _make_test("foo")
    t2 = _make_test("bar")
    t3 = _make_test("baz")
    return SuiteConfig(path=Path("/fake/tests.yaml"), tests={"foo": t1, "bar": t2, "baz": t3})


def _empty_suite():
    return SuiteConfig(path=Path("/fake/tests.yaml"), tests={})


# ---------------------------------------------------------------------------
# SelectTestsMod
# ---------------------------------------------------------------------------


def test_select_tests_all_three():
    suite = _suite3()
    mod = SelectTestsMod()
    results = list(mod.run(suite_cfg=suite, test_name=""))
    assert len(results) == 3
    assert all(port == "test" for port, _ in results)
    tests = [t for _, t in results]
    assert [t.get_name() for t in tests] == ["foo", "bar", "baz"]
    assert all(t.key == t.get_name() for t in tests)


def test_select_tests_by_name():
    suite = _suite3()
    mod = SelectTestsMod()
    results = list(mod.run(suite_cfg=suite, test_name="foo"))
    assert len(results) == 1
    port, t = results[0]
    assert port == "test"
    assert t.get_name() == "foo"
    assert t is suite.tests["foo"]


def test_select_tests_nonexistent_fatal(logging_handler):
    suite = _suite3()
    mod = SelectTestsMod()
    with pytest.raises(typer.Exit):
        list(mod.run(suite_cfg=suite, test_name="nonexistent"))


def test_select_tests_empty_suite():
    suite = _empty_suite()
    mod = SelectTestsMod()
    results = list(mod.run(suite_cfg=suite, test_name=""))
    assert results == []

"""Tests for modules/rtl_buddy/schema/suite.py and uvm.py — spec 01b acceptance criteria."""

import dataclasses
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema.uvm import UVMConfig
from modules.rtl_buddy.schema.suite import TestbenchConfig, TestConfig, SuiteConfig


def make_tb(**overrides):
	defaults = {"name": "tb_top", "filelist": ["rtl/top.sv"]}
	defaults.update(overrides)
	return TestbenchConfig(**defaults)


def make_test(**overrides):
	defaults = {
		"name": "alu",
		"desc": "ALU smoke test",
		"model": "sandbox",
		"model_path": "models.yaml",
		"suite_dir": Path("/design/verif"),
		"reglvl": None,
		"pa": None,
		"pd": None,
		"uvm": None,
		"preproc_path": None,
		"postproc_path": None,
		"sweep_path": None,
		"tb": make_tb(),
		"timeout": None,
	}
	defaults.update(overrides)
	return TestConfig(**defaults)


# ---------------------------------------------------------------------------
# UVMConfig defaults and validation
# ---------------------------------------------------------------------------


def test_uvm_defaults():
	u = UVMConfig()
	assert u.max_warns == 0
	assert u.max_errors == 0


def test_uvm_explicit_values():
	u = UVMConfig(max_warns=5, max_errors=2)
	assert u.max_warns == 5
	assert u.max_errors == 2


def test_uvm_negative_max_warns():
	with pytest.raises(ValueError):
		UVMConfig(max_warns=-1)


def test_uvm_negative_max_errors():
	with pytest.raises(ValueError):
		UVMConfig(max_errors=-1)


# ---------------------------------------------------------------------------
# TestbenchConfig getters
# ---------------------------------------------------------------------------


def test_testbench_get_name():
	tb = make_tb(name="tb_uart")
	assert tb.get_name() == "tb_uart"


def test_testbench_get_filelist():
	fl = ["rtl/top.sv", "rtl/pkg.sv"]
	tb = make_tb(filelist=fl)
	assert tb.get_filelist() == fl
	assert tb.get_filelist() is tb.filelist


# ---------------------------------------------------------------------------
# TestConfig key __post_init__ and dataclasses.replace re-key
# ---------------------------------------------------------------------------


def test_key_defaults_to_name():
	t = make_test(name="alu")
	assert t.key == "alu"


def test_key_explicit_preserved():
	t = make_test(name="alu", key="x")
	assert t.key == "x"


def test_replace_rekey():
	t = make_test(name="alu")
	replaced = dataclasses.replace(t, key="alu#0#1")
	assert replaced.key == "alu#0#1"
	assert t.key == "alu"  # original untouched
	assert replaced.tb is t.tb  # shared by reference


# ---------------------------------------------------------------------------
# get_reglvl resolution order
# ---------------------------------------------------------------------------


def test_reglvl_uniform_int():
	t = make_test(reglvl=3)
	assert t.get_reglvl("vcs") == 3
	assert t.get_reglvl("verilator") == 3


def test_reglvl_dict_with_builder():
	t = make_test(reglvl={"vcs": 5, "verilator": 2, "default": 1})
	assert t.get_reglvl("vcs") == 5


def test_reglvl_dict_with_default():
	t = make_test(reglvl={"default": 7})
	assert t.get_reglvl("vcs") == 7


def test_reglvl_none_returns_zero():
	t = make_test(reglvl=None)
	assert t.get_reglvl("vcs") == 0


def test_reglvl_malformed_dict_fatal(logging_handler):
	t = make_test(reglvl={"verilator": 3})
	with pytest.raises(typer.Exit):
		t.get_reglvl("vcs")


# ---------------------------------------------------------------------------
# get_timeout
# ---------------------------------------------------------------------------


def test_timeout_default():
	t = make_test(timeout=None)
	assert t.get_timeout() == (60, False)


def test_timeout_custom():
	t = make_test(timeout=300)
	assert t.get_timeout() == (300, True)


# ---------------------------------------------------------------------------
# Plusarg mutation (lazy init, merge, readback)
# ---------------------------------------------------------------------------


def test_plusarg_lazy_init():
	t = make_test(pa=None)
	t.set_plusarg("FOO", 1)
	assert t.pa == {"FOO": 1}


def test_plusargs_merge():
	t = make_test(pa={"X": 0})
	t.set_plusargs({"A": 1, "B": 2})
	assert t.pa == {"X": 0, "A": 1, "B": 2}


def test_plusargs_merge_lazy_init():
	t = make_test(pa=None)
	t.set_plusargs({"A": 1, "B": 2})
	assert t.pa == {"A": 1, "B": 2}


def test_plusarg_readback():
	t = make_test(pa={"K": 42})
	assert t.get_plusarg("K") == 42
	assert t.get_plusarg("missing") is None


def test_get_plusarg_raises_when_none():
	t = make_test(pa=None)
	with pytest.raises(AttributeError):
		t.get_plusarg("K")


def test_get_plusargs_returns_dict():
	t = make_test(pa={"A": 1})
	assert t.get_plusargs() == {"A": 1}


def test_get_plusargs_returns_none():
	t = make_test(pa=None)
	assert t.get_plusargs() is None


# ---------------------------------------------------------------------------
# Plusdefine mutation (symmetric to plusargs)
# ---------------------------------------------------------------------------


def test_plusdefine_lazy_init():
	t = make_test(pd=None)
	t.set_plusdefine("WIDTH", 8)
	assert t.pd == {"WIDTH": 8}


def test_plusdefines_merge():
	t = make_test(pd={"X": 0})
	t.set_plusdefines({"A": 1, "B": 2})
	assert t.pd == {"X": 0, "A": 1, "B": 2}


def test_plusdefines_merge_lazy_init():
	t = make_test(pd=None)
	t.set_plusdefines({"A": 1, "B": 2})
	assert t.pd == {"A": 1, "B": 2}


def test_plusdefine_readback():
	t = make_test(pd={"K": 42})
	assert t.get_plusdefine("K") == 42
	assert t.get_plusdefine("missing") is None


def test_get_plusdefine_raises_when_none():
	t = make_test(pd=None)
	with pytest.raises(AttributeError):
		t.get_plusdefine("K")


def test_get_plusdefines_returns_none():
	t = make_test(pd=None)
	assert t.get_plusdefines() is None


# ---------------------------------------------------------------------------
# SuiteConfig getters
# ---------------------------------------------------------------------------


def test_suite_get_tests_all():
	t1, t2 = make_test(name="a"), make_test(name="b")
	s = SuiteConfig(path=Path("/suite/tests.yaml"), tests={"a": t1, "b": t2})
	vals = s.get_tests()
	assert list(vals) == [t1, t2]


def test_suite_get_tests_by_name():
	t1 = make_test(name="a")
	s = SuiteConfig(path=Path("/suite/tests.yaml"), tests={"a": t1})
	result = s.get_tests("a")
	assert result == [t1]


def test_suite_get_tests_unknown_fatal(logging_handler):
	s = SuiteConfig(path=Path("/suite/tests.yaml"), tests={})
	with pytest.raises(typer.Exit):
		s.get_tests("nonexistent")


def test_suite_get_test_names():
	t1, t2 = make_test(name="x"), make_test(name="y")
	s = SuiteConfig(path=Path("/suite/tests.yaml"), tests={"x": t1, "y": t2})
	assert s.get_test_names() == ["x", "y"]


def test_suite_get_path():
	p = Path("/suite/tests.yaml")
	s = SuiteConfig(path=p, tests={})
	assert s.get_path() == p


# ---------------------------------------------------------------------------
# Trivial getters
# ---------------------------------------------------------------------------


def test_get_name():
	t = make_test(name="alu")
	assert t.get_name() == "alu"


def test_get_testbench():
	tb = make_tb()
	t = make_test(tb=tb)
	assert t.get_testbench() is tb


def test_get_sweep_path():
	t = make_test(sweep_path="scripts/sweep.py")
	assert t.get_sweep_path() == "scripts/sweep.py"


def test_get_preproc_path():
	t = make_test(preproc_path="scripts/pre.py")
	assert t.get_preproc_path() == "scripts/pre.py"


def test_get_postproc_path():
	t = make_test(postproc_path="scripts/post.py")
	assert t.get_postproc_path() == "scripts/post.py"


def test_set_timeout():
	t = make_test(timeout=None)
	t.set_timeout(120)
	assert t.timeout == 120
	assert t.get_timeout() == (120, True)

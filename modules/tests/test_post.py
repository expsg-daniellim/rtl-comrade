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
ParseLogMod = _mod.ParseLogMod


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


# ---------------------------------------------------------------------------
# ParseLogMod (spec 09b)
# ---------------------------------------------------------------------------


def _make_log_proc(key, log_path):
	return Proc(key=key, rc=0, stdout_path=log_path, stderr_path=Path("/tmp/sim.err"))


def test_parse_log_pass(tmp_path, logging_handler):
	log_file = tmp_path / "sim.log"
	log_file.write_text("PASS test completed\n")
	test = _make_test()
	proc = _make_log_proc(test.key, log_file)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is False


def test_parse_log_fail_with_err(tmp_path, logging_handler):
	log_file = tmp_path / "sim.log"
	log_file.write_text("FAIL sim failed\nERR: assertion at line 42\n")
	test = _make_test()
	proc = _make_log_proc(test.key, log_file)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_log_fail_wins_over_pass(tmp_path, logging_handler):
	log_file = tmp_path / "sim.log"
	log_file.write_text("PASS test ran\nFAIL assertion failed\n")
	test = _make_test()
	proc = _make_log_proc(test.key, log_file)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_log_fail_without_err_no_crash(tmp_path, logging_handler):
	log_file = tmp_path / "sim.log"
	log_file.write_text("FAIL assertion at line 99\n")
	test = _make_test()
	proc = _make_log_proc(test.key, log_file)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_log_passthrough_is_unknown(tmp_path, logging_handler):
	log_file = tmp_path / "sim.log"
	log_file.write_text("PASSTHROUGH message\n")
	test = _make_test()
	proc = _make_log_proc(test.key, log_file)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_log_no_keywords_is_unknown(tmp_path, logging_handler):
	log_file = tmp_path / "sim.log"
	log_file.write_text("INFO: simulation running\nDEBUG: checkpoint\n")
	test = _make_test()
	proc = _make_log_proc(test.key, log_file)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_log_unreadable_file(tmp_path, logging_handler):
	missing = tmp_path / "nonexistent.log"
	test = _make_test()
	proc = _make_log_proc(test.key, missing)
	result = ParseLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# ParseUvmLogMod (spec 09c)
# ---------------------------------------------------------------------------

ParseUvmLogMod = _mod.ParseUvmLogMod


def _make_uvm_test(max_warns=5, max_errors=2, name="uvmtest"):
	uvm = UVMConfig(max_warns=max_warns, max_errors=max_errors)
	return _make_test(uvm=uvm, name=name)


def _make_uvm_log(tmp_path, warns=0, errors=0, fatal=0, info=10, filename="uvm.log"):
	log_file = tmp_path / filename
	log_file.write_text(
		f"--------- UVM Report Summary ---------\n"
		f"** Report counts by severity\n"
		f"UVM_INFO   : {info}\n"
		f"UVM_WARNING : {warns}\n"
		f"UVM_ERROR   : {errors}\n"
		f"UVM_FATAL  : {fatal}\n"
	)
	return log_file


def _make_uvm_proc(key, log_path):
	return Proc(key=key, rc=0, stdout_path=log_path, stderr_path=Path("/tmp/sim.err"))


def test_parse_uvm_log_all_zero_pass(tmp_path, logging_handler):
	test = _make_uvm_test(max_warns=5, max_errors=2)
	log_file = _make_uvm_log(tmp_path, warns=0, errors=0, fatal=0)
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is False


def test_parse_uvm_log_boundary_pass(tmp_path, logging_handler):
	test = _make_uvm_test(max_warns=2, max_errors=1)
	log_file = _make_uvm_log(tmp_path, warns=2, errors=1, fatal=0)
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is False


def test_parse_uvm_log_error_over_threshold_fail(tmp_path, logging_handler):
	test = _make_uvm_test(max_warns=5, max_errors=2)
	log_file = _make_uvm_log(tmp_path, warns=0, errors=3, fatal=0)
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_uvm_log_warn_over_threshold_fail(tmp_path, logging_handler):
	test = _make_uvm_test(max_warns=1, max_errors=5)
	log_file = _make_uvm_log(tmp_path, warns=2, errors=0, fatal=0)
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_uvm_log_fatal_nonzero_fail(tmp_path, logging_handler):
	test = _make_uvm_test(max_warns=5, max_errors=5)
	log_file = _make_uvm_log(tmp_path, warns=0, errors=0, fatal=1)
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_uvm_log_no_summary_block(tmp_path, logging_handler):
	log_file = tmp_path / "uvm.log"
	log_file.write_text("simulation running\ntest completed\n")
	test = _make_uvm_test()
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_uvm_log_invalid_summary_missing_severity(tmp_path, logging_handler):
	log_file = tmp_path / "uvm.log"
	log_file.write_text(
		"--------- UVM Report Summary ---------\n"
		"** Report counts by severity\n"
		"UVM_INFO   : 10\n"
		"UVM_WARNING : 2\n"
		"UVM_ERROR   : 0\n"
	)
	test = _make_uvm_test()
	proc = _make_uvm_proc(test.key, log_file)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True


def test_parse_uvm_log_unreadable_file(tmp_path, logging_handler):
	missing = tmp_path / "nonexistent_uvm.log"
	test = _make_uvm_test()
	proc = _make_uvm_proc(test.key, missing)
	result = ParseUvmLogMod().run(test=test, proc=proc)
	assert result is None
	assert logging_handler.failure is True

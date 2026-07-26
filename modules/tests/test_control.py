"""Tests for modules/rtl_buddy/control.py — EarlyStopGateMod (spec 10a)."""

import importlib.util
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import structlog.testing
import typer

from modules.rtl_buddy.schema import TestResult, RunDepth, ModelConfig, Proc
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig

_spec = importlib.util.spec_from_file_location(
	"modules_rtl_buddy_control",
	Path(__file__).parent.parent / "rtl_buddy" / "control.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
EarlyStopGateMod = _mod.EarlyStopGateMod


def _make_tb():
	return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


def _make_test(name="t1"):
	return TestConfig(
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


def _make_model():
	return ModelConfig(name="sandbox", filelist=["rtl/model.sv"])


def _make_simv():
	return "/build/obj_dir_t1/simv"


def _make_proc(key, tmp_path):
	return Proc(key=key, rc=0, stdout_path=str(tmp_path / "sim.log"), stderr_path=str(tmp_path / "sim.err"))


def _make_mod(phase):
	return EarlyStopGateMod(config=EarlyStopGateMod.Config(phase=phase))


_ORDER = [d.value for d in RunDepth]  # ["pre", "comp", "sim", "post"]


# ---------------------------------------------------------------------------
# Parametrised matrix — all three phases × all four early_stop values
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("phase,early_stop", [
	(phase, es) for phase in ("pre", "comp", "sim") for es in ("pre", "comp", "sim", "post")
])
def test_matrix(phase, early_stop, tmp_path):
	test = _make_test()
	if phase == "pre":
		edges = {"test": test, "model": _make_model()}
	elif phase == "comp":
		edges = {"test": test, "simv": _make_simv()}
	else:
		edges = {"test": test, "proc": _make_proc(test.key, tmp_path)}

	mod = _make_mod(phase)
	results = list(mod.run(early_stop=early_stop, **edges))
	should_stop = _ORDER.index(early_stop) <= _ORDER.index(phase)

	if should_stop:
		assert len(results) == 1
		port, val = results[0]
		assert port == "stop"
		assert val == TestResult.early_stop(test.key, test.get_name(), f"Stopped early at {phase}")
	else:
		assert len(results) == len(edges)
		result_dict = dict(results)
		for name, payload in edges.items():
			assert result_dict[name] == payload


# ---------------------------------------------------------------------------
# Co-gating — gate-pre: go forwards both edges, stop drops both
# ---------------------------------------------------------------------------


def test_cogate_pre_go():
	test = _make_test()
	model = _make_model()
	mod = _make_mod("pre")
	results = list(mod.run(early_stop="comp", test=test, model=model))
	assert len(results) == 2
	assert ("test", test) in results
	assert ("model", model) in results


def test_cogate_pre_stop():
	test = _make_test()
	model = _make_model()
	mod = _make_mod("pre")
	results = list(mod.run(early_stop="pre", test=test, model=model))
	assert len(results) == 1
	port, val = results[0]
	assert port == "stop"
	assert val == TestResult.early_stop(test.key, test.get_name(), "Stopped early at pre")


# ---------------------------------------------------------------------------
# Co-gating — gate-comp: go forwards both edges, stop drops both
# ---------------------------------------------------------------------------


def test_cogate_comp_go():
	test = _make_test()
	simv = _make_simv()
	mod = _make_mod("comp")
	results = list(mod.run(early_stop="sim", test=test, simv=simv))
	assert len(results) == 2
	assert ("test", test) in results
	assert ("simv", simv) in results


def test_cogate_comp_stop():
	test = _make_test()
	simv = _make_simv()
	mod = _make_mod("comp")
	results = list(mod.run(early_stop="comp", test=test, simv=simv))
	assert len(results) == 1
	port, val = results[0]
	assert port == "stop"
	assert val == TestResult.early_stop(test.key, test.get_name(), "Stopped early at comp")


# ---------------------------------------------------------------------------
# Co-gating — gate-sim: go forwards both edges, stop drops both
# ---------------------------------------------------------------------------


def test_cogate_sim_go(tmp_path):
	test = _make_test()
	proc = _make_proc(test.key, tmp_path)
	mod = _make_mod("sim")
	results = list(mod.run(early_stop="post", test=test, proc=proc))
	assert len(results) == 2
	assert ("test", test) in results
	assert ("proc", proc) in results


def test_cogate_sim_stop(tmp_path):
	test = _make_test()
	proc = _make_proc(test.key, tmp_path)
	mod = _make_mod("sim")
	results = list(mod.run(early_stop="sim", test=test, proc=proc))
	assert len(results) == 1
	port, val = results[0]
	assert port == "stop"
	assert val == TestResult.early_stop(test.key, test.get_name(), "Stopped early at sim")


# ---------------------------------------------------------------------------
# Boundary: own-phase stop is inclusive (early_stop <= phase → stop)
# ---------------------------------------------------------------------------


def test_own_phase_stops():
	test = _make_test()
	simv = _make_simv()
	mod = _make_mod("comp")
	results = list(mod.run(early_stop="comp", test=test, simv=simv))
	assert len(results) == 1
	port, _ = results[0]
	assert port == "stop"


# ---------------------------------------------------------------------------
# Boundary: default early_stop="post" never stops any phase
# ---------------------------------------------------------------------------


def test_default_post_never_stops_pre():
	test = _make_test()
	model = _make_model()
	mod = _make_mod("pre")
	results = list(mod.run(test=test, model=model))
	assert all(port != "stop" for port, _ in results)
	assert len(results) == 2


def test_default_post_never_stops_comp():
	test = _make_test()
	simv = _make_simv()
	mod = _make_mod("comp")
	results = list(mod.run(test=test, simv=simv))
	assert all(port != "stop" for port, _ in results)
	assert len(results) == 2


def test_default_post_never_stops_sim(tmp_path):
	test = _make_test()
	proc = _make_proc(test.key, tmp_path)
	mod = _make_mod("sim")
	results = list(mod.run(test=test, proc=proc))
	assert all(port != "stop" for port, _ in results)
	assert len(results) == 2


# ---------------------------------------------------------------------------
# Stop emits no log.error/log.fatal — logging_handler.failure stays False
# ---------------------------------------------------------------------------


def test_stop_no_failure(logging_handler):
	test = _make_test()
	simv = _make_simv()
	mod = _make_mod("comp")
	results = list(mod.run(early_stop="comp", test=test, simv=simv))
	assert len(results) == 1
	assert logging_handler.failure is False


# ---------------------------------------------------------------------------
# Invalid early_stop → log.fatal → typer.Exit
# ---------------------------------------------------------------------------


def test_invalid_early_stop(logging_handler):
	test = _make_test()
	simv = _make_simv()
	mod = _make_mod("comp")
	with pytest.raises(typer.Exit):
		list(mod.run(early_stop="bogus", test=test, simv=simv))


# ---------------------------------------------------------------------------
# GitStatusMod (spec 10b)
# ---------------------------------------------------------------------------

_setup_spec = importlib.util.spec_from_file_location(
	"modules_rtl_buddy_setup",
	Path(__file__).parent.parent / "rtl_buddy" / "setup.py",
)
assert _setup_spec is not None
assert _setup_spec.loader is not None
_setup_mod = importlib.util.module_from_spec(_setup_spec)
_setup_spec.loader.exec_module(_setup_mod)
GitStatusMod = _setup_mod.GitStatusMod


def _init_git_repo(path):
	subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
	subprocess.run(["git", "-C", str(path), "config", "user.email", "test@test.com"], check=True, capture_output=True)
	subprocess.run(["git", "-C", str(path), "config", "user.name", "Test"], check=True, capture_output=True)
	subprocess.run(["git", "-C", str(path), "commit", "--allow-empty", "-m", "init"], check=True, capture_output=True)


def test_git_status_clean(tmp_path, monkeypatch):
	_init_git_repo(tmp_path)
	monkeypatch.chdir(tmp_path)
	with structlog.testing.capture_logs() as logs:
		result = GitStatusMod().run()
	assert result == ("default", True)
	git_events = [e for e in logs if e.get("event") == "git_state"]
	assert len(git_events) == 1
	assert git_events[0]["dirty"] is False
	assert not any(e.get("log_level") in ("warning", "error", "critical") for e in logs)


def test_git_status_dirty(tmp_path, monkeypatch):
	_init_git_repo(tmp_path)
	(tmp_path / "dirty.txt").write_text("change")
	monkeypatch.chdir(tmp_path)
	with structlog.testing.capture_logs() as logs:
		result = GitStatusMod().run()
	assert result == ("default", True)
	git_events = [e for e in logs if e.get("event") == "git_state"]
	assert len(git_events) == 1
	assert git_events[0]["dirty"] is True


def test_git_status_not_a_repo(tmp_path, monkeypatch, logging_handler):
	monkeypatch.chdir(tmp_path)
	result = GitStatusMod().run()
	assert result == ("default", True)
	assert logging_handler.failure is False


def test_git_status_git_unavailable(logging_handler):
	with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
		result = GitStatusMod().run()
	assert result == ("default", True)
	assert logging_handler.failure is False

"""Tests for modules/rtl_buddy/build.py — BuildCompileCmdMod (spec 07a)."""

import importlib.util
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema import KeyedValue, Command, TestResult, Proc
from modules.rtl_buddy.schema.builder import RtlBuilderConfig, RtlBuilderConfigOpts
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_build",
    Path(__file__).parent.parent / "rtl_buddy" / "build.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
BuildCompileCmdMod = _mod.BuildCompileCmdMod
InterpretCompileMod = _mod.InterpretCompileMod


def _make_tb():
    return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


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


def _make_builder_cfg(exe="vcs", simv="simv", compile_opts=None):
    return RtlBuilderConfig(
        name="vcs",
        exe=exe,
        simv=simv,
        sim_rand_seed=12345,
        sim_rand_prefix="+ntb_random_seed=",
        opts={"debug": RtlBuilderConfigOpts(compile_time=compile_opts or ["-Wall"], run_time=["-debug"])},
    )


# ---------------------------------------------------------------------------
# Non-verilator, no plusdefines
# ---------------------------------------------------------------------------


def test_non_verilator_no_plusdefines(tmp_path):
    test = _make_test("basic")
    filelist = KeyedValue(test.key, tmp_path / "run.basic.f")
    builder_cfg = _make_builder_cfg()
    logs_dir = tmp_path / "logs"
    mod = BuildCompileCmdMod()
    results = list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path))
    assert len(results) == 3
    assert results[0] == ("test", test)
    port_simv, kv_simv = results[1]
    assert port_simv == "simv"
    assert kv_simv.key == test.key
    assert kv_simv.value == builder_cfg.get_simv()
    port_cmd, cmd = results[2]
    assert port_cmd == "command"
    assert cmd.argv == ["vcs", "-Wall", "-f", str(filelist.value)]
    assert "--Mdir" not in cmd.argv


# ---------------------------------------------------------------------------
# Verilator: --Mdir in argv, simv from build_dir
# ---------------------------------------------------------------------------


def test_verilator_build_dir_and_simv(tmp_path):
    test = _make_test("basic")
    filelist = KeyedValue(test.key, tmp_path / "run.basic.f")
    builder_cfg = _make_builder_cfg(exe="verilator")
    logs_dir = tmp_path / "logs"
    mod = BuildCompileCmdMod()
    results = list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path))
    assert len(results) == 3
    test_tag = "basic"
    expected_build_dir = str(tmp_path / f"obj_dir_{test_tag}")
    expected_simv = f"{expected_build_dir}/simv"
    port_simv, kv_simv = results[1]
    assert port_simv == "simv"
    assert kv_simv.value == expected_simv
    port_cmd, cmd = results[2]
    assert "--Mdir" in cmd.argv
    mdir_idx = cmd.argv.index("--Mdir")
    assert cmd.argv[mdir_idx + 1] == expected_build_dir


# ---------------------------------------------------------------------------
# build_dir / simv rooted on work_dir, not process CWD
# ---------------------------------------------------------------------------


def test_work_dir_rooting(tmp_path, monkeypatch):
    other = tmp_path / "other"
    other.mkdir()
    monkeypatch.chdir(other)
    test = _make_test("root_test")
    filelist = KeyedValue(test.key, tmp_path / "run.root_test.f")
    builder_cfg = _make_builder_cfg(exe="verilator")
    logs_dir = tmp_path / "logs"
    mod = BuildCompileCmdMod()
    results = list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path))
    test_tag = "root_test"
    expected_build_dir = str(tmp_path / f"obj_dir_{test_tag}")
    port_simv, kv_simv = results[1]
    assert kv_simv.value == f"{expected_build_dir}/simv"
    port_cmd, cmd = results[2]
    mdir_idx = cmd.argv.index("--Mdir")
    assert cmd.argv[mdir_idx + 1] == expected_build_dir
    assert str(other) not in cmd.argv[mdir_idx + 1]


# ---------------------------------------------------------------------------
# plusdefines formatting: None-valued define omits =
# ---------------------------------------------------------------------------


def test_plusdefines_formatting(tmp_path):
    test = _make_test("pd", pd={"FOO": 1, "BAR": None})
    filelist = KeyedValue(test.key, tmp_path / "run.pd.f")
    builder_cfg = _make_builder_cfg()
    logs_dir = tmp_path / "logs"
    mod = BuildCompileCmdMod()
    results = list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path))
    port_cmd, cmd = results[2]
    assert "+define+FOO=1" in cmd.argv
    assert "+define+BAR" in cmd.argv
    assert "+define+BAR=None" not in cmd.argv


# ---------------------------------------------------------------------------
# logs_dir is a resolved Path: log filenames are joined onto it
# ---------------------------------------------------------------------------


def test_custom_logs_dir(tmp_path):
    logs_dir = Path("/work/custom")
    test = _make_test("basic")
    filelist = KeyedValue(test.key, tmp_path / "run.basic.f")
    builder_cfg = _make_builder_cfg()
    mod = BuildCompileCmdMod()
    results = list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path))
    port_cmd, cmd = results[2]
    assert cmd.stdout_path == "/work/custom/basic.compile.log"
    assert cmd.stderr_path == "/work/custom/basic.compile.err"


# ---------------------------------------------------------------------------
# test_tag regex: shell-unsafe chars sanitized in build_dir, simv, log paths
# ---------------------------------------------------------------------------


def test_test_tag_sanitization(tmp_path):
    test = _make_test("a/b:c")
    filelist = KeyedValue(test.key, tmp_path / "run.a_b_c.f")
    builder_cfg = _make_builder_cfg(exe="verilator")
    logs_dir = tmp_path / "logs"
    mod = BuildCompileCmdMod()
    results = list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path))
    test_tag = "a_b_c"
    expected_build_dir = str(tmp_path / f"obj_dir_{test_tag}")
    port_simv, kv_simv = results[1]
    assert kv_simv.value == f"{expected_build_dir}/simv"
    port_cmd, cmd = results[2]
    assert cmd.stdout_path.endswith(f"{test_tag}.compile.log")
    assert cmd.stderr_path.endswith(f"{test_tag}.compile.err")
    mdir_idx = cmd.argv.index("--Mdir")
    assert cmd.argv[mdir_idx + 1] == expected_build_dir


# ---------------------------------------------------------------------------
# Unknown builder_mode: get_compile_time_opts log.fatals → typer.Exit
# ---------------------------------------------------------------------------


def test_bad_builder_mode(tmp_path, logging_handler):
    test = _make_test("basic")
    filelist = KeyedValue(test.key, tmp_path / "run.basic.f")
    builder_cfg = _make_builder_cfg()
    logs_dir = tmp_path / "logs"
    mod = BuildCompileCmdMod()
    with pytest.raises(typer.Exit):
        list(mod.run(test=test, filelist=filelist, builder_cfg=builder_cfg, logs_dir=logs_dir, work_dir=tmp_path, builder_mode="nonexistent"))


# ---------------------------------------------------------------------------
# InterpretCompileMod (spec 07b)
# ---------------------------------------------------------------------------


def _make_proc(key, rc, tmp_path, stderr_content=None):
    stdout_path = tmp_path / "compile.log"
    stderr_path = tmp_path / "compile.err"
    if stderr_content is not None:
        stderr_path.write_text(stderr_content)
    return Proc(key=key, rc=rc, stdout_path=str(stdout_path), stderr_path=str(stderr_path))


def test_interpret_compile_success(tmp_path):
    test = _make_test("t1")
    simv = KeyedValue(test.key, "/build/obj_dir_t1/simv")
    proc = _make_proc(test.key, rc=0, tmp_path=tmp_path, stderr_content="")
    mod = InterpretCompileMod()
    results = list(mod.run(test=test, simv=simv, proc=proc))
    assert results == [("test", test), ("simv", simv)]


def test_interpret_compile_fail_rc2_with_stderr(tmp_path, logging_handler):
    test = _make_test("t1")
    simv = KeyedValue(test.key, "/build/obj_dir_t1/simv")
    proc = _make_proc(test.key, rc=2, tmp_path=tmp_path, stderr_content="Error: syntax error near 'module'\n")
    mod = InterpretCompileMod()
    results = list(mod.run(test=test, simv=simv, proc=proc))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert val == TestResult.compile_fail(test.key, test.get_name())
    assert logging_handler.failure is True


def test_interpret_compile_signal_fail(tmp_path, logging_handler):
    test = _make_test("t1")
    simv = KeyedValue(test.key, "/build/obj_dir_t1/simv")
    proc = _make_proc(test.key, rc=-11, tmp_path=tmp_path, stderr_content="Segmentation fault\n")
    mod = InterpretCompileMod()
    results = list(mod.run(test=test, simv=simv, proc=proc))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert isinstance(val, TestResult)
    assert val == TestResult.compile_fail(test.key, test.get_name())
    assert logging_handler.failure is True


def test_interpret_compile_missing_stderr(tmp_path, logging_handler):
    test = _make_test("t1")
    simv = KeyedValue(test.key, "/build/obj_dir_t1/simv")
    proc = Proc(key=test.key, rc=1, stdout_path=str(tmp_path / "compile.log"), stderr_path=str(tmp_path / "missing.err"))
    mod = InterpretCompileMod()
    results = list(mod.run(test=test, simv=simv, proc=proc))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert isinstance(val, TestResult)
    assert val == TestResult.compile_fail(test.key, test.get_name())
    assert logging_handler.failure is True

"""Tests for modules/rtl_buddy/sim.py — ExpandRunsMod (spec 08a), ResolveSeedMod (spec 08b), BuildSimCmdMod (spec 08c)."""

import importlib.util
import random
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema import KeyedValue, SeedMode, TestResult, RandSeed
from modules.rtl_buddy.schema.builder import RtlBuilderConfig, RtlBuilderConfigOpts
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
ResolveSeedMod = _mod.ResolveSeedMod
run_suffix = _mod.run_suffix
BuildSimCmdMod = _mod.BuildSimCmdMod


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


# ---------------------------------------------------------------------------
# ResolveSeedMod (spec 08b)
# ---------------------------------------------------------------------------


def _make_builder_cfg_rs(seed=99999):
    return RtlBuilderConfig(
        name="vcs", exe="vcs", simv="simv",
        sim_rand_seed=seed,
        sim_rand_prefix="+ntb_random_seed=",
        opts={"debug": RtlBuilderConfigOpts(compile_time=["-Wall"], run_time=["-debug"])},
    )


def _make_run_id_kv(key, value=None):
    return KeyedValue(key, value)


def test_resolve_seed_new(monkeypatch):
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    builder_cfg = _make_builder_cfg_rs()
    monkeypatch.setattr(random, "randrange", lambda n: 42000)
    mod = ResolveSeedMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.NEW, builder_cfg=builder_cfg, logs_dir=Path("/unused")))
    assert len(results) == 4
    assert results[0] == ("test", test)
    assert results[1] == ("run_id", run_id)
    assert results[2] == ("simv", simv)
    port, kv = results[3]
    assert port == "seed"
    assert kv.key == test.key
    assert kv.value == 42000
    assert 0 <= kv.value < 1_000_000


def test_resolve_seed_default():
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    builder_cfg = _make_builder_cfg_rs(seed=77777)
    mod = ResolveSeedMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.DEFAULT, builder_cfg=builder_cfg, logs_dir=Path("/unused")))
    assert len(results) == 4
    assert results[0] == ("test", test)
    assert results[1] == ("run_id", run_id)
    assert results[2] == ("simv", simv)
    port, kv = results[3]
    assert port == "seed"
    assert kv.key == test.key
    assert kv.value == 77777


def test_resolve_seed_replay_round_trip(tmp_path):
    test = _make_test()
    run_id = _make_run_id_kv(test.key, value=3)
    simv = _make_simv(test.key)
    builder_cfg = _make_builder_cfg_rs()
    seed_path = tmp_path / f"{test.get_name()}_0003.randseed"
    seed_path.write_text("55555\n")
    mod = ResolveSeedMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.REPLAY, builder_cfg=builder_cfg, logs_dir=tmp_path))
    assert len(results) == 4
    assert results[0] == ("test", test)
    assert results[1] == ("run_id", run_id)
    assert results[2] == ("simv", simv)
    port, kv = results[3]
    assert port == "seed"
    assert kv.key == test.key
    assert kv.value == 55555


def test_resolve_seed_replay_custom_logs_dir(tmp_path):
    custom_dir = tmp_path / "custom_logs"
    custom_dir.mkdir()
    test = _make_test()
    run_id = _make_run_id_kv(test.key)  # value=None → no suffix
    simv = _make_simv(test.key)
    builder_cfg = _make_builder_cfg_rs()
    seed_path = custom_dir / f"{test.get_name()}.randseed"
    seed_path.write_text("12345\n")
    mod = ResolveSeedMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.REPLAY, builder_cfg=builder_cfg, logs_dir=custom_dir))
    assert len(results) == 4
    port, kv = results[3]
    assert port == "seed"
    assert kv.value == 12345


def test_resolve_seed_replay_missing_file(tmp_path, logging_handler):
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    builder_cfg = _make_builder_cfg_rs()
    mod = ResolveSeedMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.REPLAY, builder_cfg=builder_cfg, logs_dir=tmp_path))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert isinstance(val, TestResult)
    assert val.result == "FAIL"
    expected_path = tmp_path / f"{test.get_name()}.randseed"
    assert str(expected_path) in val.desc
    assert logging_handler.failure is True


def test_resolve_seed_replay_malformed(tmp_path, logging_handler):
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    builder_cfg = _make_builder_cfg_rs()
    seed_path = tmp_path / f"{test.get_name()}.randseed"
    seed_path.write_text("not_an_int\n")
    mod = ResolveSeedMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.REPLAY, builder_cfg=builder_cfg, logs_dir=tmp_path))
    assert len(results) == 1
    port, val = results[0]
    assert port == "fail"
    assert isinstance(val, TestResult)
    assert val.result == "FAIL"
    assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# BuildSimCmdMod (spec 08c)
# ---------------------------------------------------------------------------


def test_build_sim_cmd_default():
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    seed = KeyedValue(test.key, 42)
    builder_cfg = _make_builder_cfg_rs()
    mod = BuildSimCmdMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="debug", logs_dir=Path("/logs")))
    assert len(results) == 4
    assert results[0] == ("test", test)
    port_c, cmd = results[1]
    assert port_c == "command"
    expected_argv = [simv.value, *builder_cfg.get_run_time_opts("debug", seed=seed.value)]
    assert cmd.argv == expected_argv
    port_to, kv_to = results[2]
    assert port_to == "timeout"
    assert kv_to.value == 60.0
    port_rs, rs = results[3]
    assert port_rs == "randseed"
    assert rs.seed == seed.value
    assert rs.argv == expected_argv
    assert rs.randseed_path.endswith(".randseed")
    assert cmd.stdout_path.endswith(".log")
    assert cmd.stderr_path.endswith(".err")


def test_build_sim_cmd_custom_timeout(logging_handler):
    test = _make_test(timeout=300)
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    seed = KeyedValue(test.key, 42)
    builder_cfg = _make_builder_cfg_rs()
    mod = BuildSimCmdMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="debug", logs_dir=Path("/logs")))
    assert len(results) == 4
    port_to, kv_to = results[2]
    assert port_to == "timeout"
    assert kv_to.value == 300.0


def test_build_sim_cmd_plusargs_plusdefines():
    test = _make_test(pa={"X": 5, "Y": None}, pd={"D": None})
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    seed = KeyedValue(test.key, 42)
    builder_cfg = _make_builder_cfg_rs()
    mod = BuildSimCmdMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="debug", logs_dir=Path("/logs")))
    port_c, cmd = results[1]
    assert "+X=5" in cmd.argv
    assert "+Y" in cmd.argv
    assert "+define+D" in cmd.argv
    assert "+Y=None" not in cmd.argv
    assert "+define+D=None" not in cmd.argv


def test_build_sim_cmd_custom_logs_dir():
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    seed = KeyedValue(test.key, 42)
    builder_cfg = _make_builder_cfg_rs()
    mod = BuildSimCmdMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="debug", logs_dir=Path("/work/custom")))
    port_c, cmd = results[1]
    assert cmd.stdout_path.startswith("/work/custom/")
    assert cmd.stderr_path.startswith("/work/custom/")
    port_rs, rs = results[3]
    assert rs.randseed_path.startswith("/work/custom/")


def test_build_sim_cmd_run_id_suffix():
    test = _make_test()
    run_id = _make_run_id_kv(test.key, value=5)
    simv = _make_simv(test.key)
    seed = KeyedValue(test.key, 42)
    builder_cfg = _make_builder_cfg_rs()
    mod = BuildSimCmdMod()
    results = list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="debug", logs_dir=Path("/logs")))
    port_c, cmd = results[1]
    port_rs, rs = results[3]
    assert "_0005" in cmd.stdout_path
    assert "_0005" in cmd.stderr_path
    assert "_0005" in rs.randseed_path
    assert rs.argv == cmd.argv


def test_build_sim_cmd_bad_builder_mode(logging_handler):
    test = _make_test()
    run_id = _make_run_id_kv(test.key)
    simv = _make_simv(test.key)
    seed = KeyedValue(test.key, 42)
    builder_cfg = _make_builder_cfg_rs()
    mod = BuildSimCmdMod()
    with pytest.raises(typer.Exit):
        list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="nonexistent", logs_dir=Path("/logs")))

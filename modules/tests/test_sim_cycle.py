"""Tests for modules/rtl_buddy/sim.py — ExpandRunsMod (spec 08a), ResolveSeedMod (spec 08b), BuildSimCmdMod (spec 08c)."""

import importlib.util
import os
import random
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema import KeyedValue, SeedMode, TestResult, Proc, RandSeed, RandSeedDone
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
WriteRandseedMod = _mod.WriteRandseedMod
LinkLatestMod = _mod.LinkLatestMod


def _make_tb():
	return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


def _make_test(name="mytest", **overrides):
	defaults = {
		"name": name,
		"desc": f"{name} test",
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
		"tb": _make_tb(),
		"timeout": None,
	}
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
	_, val_t = results[0]
	_, val_r = results[1]
	_, val_s = results[2]
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


def test_resolve_seed_replay_permission_error(tmp_path, logging_handler):
	test = _make_test()
	run_id = _make_run_id_kv(test.key)
	simv = _make_simv(test.key)
	builder_cfg = _make_builder_cfg_rs()
	seed_path = tmp_path / f"{test.get_name()}.randseed"
	seed_path.write_text("12345\n")
	seed_path.chmod(0o000)
	mod = ResolveSeedMod()
	try:
		results = list(mod.run(test=test, run_id=run_id, simv=simv, seed_mode=SeedMode.REPLAY, builder_cfg=builder_cfg, logs_dir=tmp_path))
	finally:
		seed_path.chmod(0o644)
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
	_, cmd = results[1]
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
	_, cmd = results[1]
	assert cmd.stdout_path.startswith("/work/custom/")
	assert cmd.stderr_path.startswith("/work/custom/")
	_, rs = results[3]
	assert rs.randseed_path.startswith("/work/custom/")


def test_build_sim_cmd_run_id_suffix():
	test = _make_test()
	run_id = _make_run_id_kv(test.key, value=5)
	simv = _make_simv(test.key)
	seed = KeyedValue(test.key, 42)
	builder_cfg = _make_builder_cfg_rs()
	mod = BuildSimCmdMod()
	results = list(mod.run(test=test, run_id=run_id, simv=simv, seed=seed, builder_cfg=builder_cfg, builder_mode="debug", logs_dir=Path("/logs")))
	_, cmd = results[1]
	_, rs = results[3]
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


# ---------------------------------------------------------------------------
# WriteRandseedMod (spec 08d)
# ---------------------------------------------------------------------------


def _make_randseed(key, tmp_path, seed=12345, argv=None):
	if argv is None:
		argv = ["/build/simv", "+ntb_random_seed=12345"]
	rs_path = str(tmp_path / f"{key}.randseed")
	return RandSeed(key=key, seed=seed, randseed_path=rs_path, argv=argv)


def _make_proc(key):
	return Proc(key=key, rc=0, stdout_path=Path("/tmp/sim.log"), stderr_path=Path("/tmp/sim.err"))


def test_write_randseed_no_hier_inst_seed(tmp_path):
	key = "mytest"
	randseed = _make_randseed(key, tmp_path)
	proc = _make_proc(key)
	mod = WriteRandseedMod()
	result = mod.run(randseed=randseed, proc=proc, work_dir=tmp_path)
	assert result == ("randseed_done", RandSeedDone(key))
	assert Path(randseed.randseed_path).read_text(encoding="utf-8") == f"{randseed.seed}\n"


def test_write_randseed_custom_logs_dir(tmp_path):
	key = "mytest"
	custom_logs = tmp_path / "custom_logs"
	custom_logs.mkdir()
	rs_path = str(custom_logs / "mytest.randseed")
	randseed = RandSeed(key=key, seed=99, randseed_path=rs_path, argv=["/simv"])
	proc = _make_proc(key)
	mod = WriteRandseedMod()
	mod.run(randseed=randseed, proc=proc, work_dir=tmp_path)
	assert Path(rs_path).read_text(encoding="utf-8") == "99\n"


def test_write_randseed_hier_inst_seed_appended(tmp_path):
	key = "mytest"
	argv = ["/build/simv", "hier_inst_seed"]
	randseed = _make_randseed(key, tmp_path, seed=42, argv=argv)
	proc = _make_proc(key)
	hier_file = tmp_path / "HierInstanceSeed.txt"
	hier_file.write_text("inst_a 111\ninst_b 222\n")
	mod = WriteRandseedMod()
	result = mod.run(randseed=randseed, proc=proc, work_dir=tmp_path)
	assert result == ("randseed_done", RandSeedDone(key))
	content = Path(randseed.randseed_path).read_text(encoding="utf-8")
	assert content.startswith(f"{randseed.seed}\n")
	assert "inst_a 111\n" in content
	assert "inst_b 222\n" in content


def test_write_randseed_reads_from_work_dir_not_cwd(tmp_path, monkeypatch):
	other_dir = tmp_path / "other"
	other_dir.mkdir()
	work_dir = tmp_path / "work"
	work_dir.mkdir()
	key = "mytest"
	argv = ["/build/simv", "hier_inst_seed"]
	randseed = RandSeed(key=key, seed=7, randseed_path=str(work_dir / "mytest.randseed"), argv=argv)
	proc = _make_proc(key)
	(work_dir / "HierInstanceSeed.txt").write_text("inst_x 555\n")
	monkeypatch.chdir(other_dir)
	mod = WriteRandseedMod()
	result = mod.run(randseed=randseed, proc=proc, work_dir=work_dir)
	assert result == ("randseed_done", RandSeedDone(key))
	content = Path(randseed.randseed_path).read_text(encoding="utf-8")
	assert "inst_x 555\n" in content


def test_write_randseed_no_hier_inst_seed_in_argv_no_open(tmp_path):
	key = "mytest"
	argv = ["/build/simv", "+ntb_random_seed=5"]
	randseed = _make_randseed(key, tmp_path, seed=5, argv=argv)
	proc = _make_proc(key)
	# HierInstanceSeed.txt is intentionally absent — if opened, an OSError would result
	mod = WriteRandseedMod()
	result = mod.run(randseed=randseed, proc=proc, work_dir=tmp_path)
	assert result == ("randseed_done", RandSeedDone(key))
	assert Path(randseed.randseed_path).read_text(encoding="utf-8") == f"{randseed.seed}\n"


def test_write_randseed_missing_hier_inst_seed_file(tmp_path, logging_handler):
	key = "mytest"
	argv = ["/build/simv", "hier_inst_seed"]
	randseed = _make_randseed(key, tmp_path, seed=3, argv=argv)
	proc = _make_proc(key)
	# HierInstanceSeed.txt is absent — FileNotFoundError should be caught
	mod = WriteRandseedMod()
	result = mod.run(randseed=randseed, proc=proc, work_dir=tmp_path)
	assert result == ("randseed_done", RandSeedDone(key))
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# LinkLatestMod (spec 08e)
# ---------------------------------------------------------------------------


def _make_link_proc(key, work_dir):
	log_path = work_dir / f"{key}.log"
	err_path = work_dir / f"{key}.err"
	log_path.write_text("stdout")
	err_path.write_text("stderr")
	return Proc(key=key, rc=0, stdout_path=log_path, stderr_path=err_path)


def _make_link_randseed(key, work_dir):
	rs_path = work_dir / f"{key}.randseed"
	rs_path.write_text("12345\n")
	return RandSeed(key=key, seed=12345, randseed_path=str(rs_path), argv=["/simv"])


def test_link_latest_fresh_work_dir(tmp_path):
	key = "mytest"
	proc = _make_link_proc(key, tmp_path)
	randseed = _make_link_randseed(key, tmp_path)
	randseed_done = RandSeedDone(key)
	mod = LinkLatestMod()
	result = mod.run(randseed=randseed, proc=proc, randseed_done=randseed_done, work_dir=tmp_path)
	assert result is None
	assert (tmp_path / "test.log").is_symlink()
	assert (tmp_path / "test.err").is_symlink()
	assert (tmp_path / "test.randseed").is_symlink()
	assert os.readlink(tmp_path / "test.log") == str(proc.stdout_path)
	assert os.readlink(tmp_path / "test.err") == str(proc.stderr_path)
	assert os.readlink(tmp_path / "test.randseed") == randseed.randseed_path


def test_link_latest_links_land_in_work_dir_not_cwd(tmp_path, monkeypatch):
	other = tmp_path / "other"
	other.mkdir()
	work = tmp_path / "work"
	work.mkdir()
	key = "mytest"
	proc = _make_link_proc(key, work)
	randseed = _make_link_randseed(key, work)
	randseed_done = RandSeedDone(key)
	monkeypatch.chdir(other)
	mod = LinkLatestMod()
	mod.run(randseed=randseed, proc=proc, randseed_done=randseed_done, work_dir=work)
	assert (work / "test.log").is_symlink()
	assert (work / "test.err").is_symlink()
	assert (work / "test.randseed").is_symlink()
	assert not (other / "test.log").exists()
	assert not (other / "test.err").exists()
	assert not (other / "test.randseed").exists()


def test_link_latest_replaces_existing_links(tmp_path):
	key = "mytest"
	old_log = tmp_path / "old.log"
	old_err = tmp_path / "old.err"
	old_rs = tmp_path / "old.randseed"
	old_log.write_text("old")
	old_err.write_text("old")
	old_rs.write_text("old")
	(tmp_path / "test.log").symlink_to(old_log)
	(tmp_path / "test.err").symlink_to(old_err)
	(tmp_path / "test.randseed").symlink_to(old_rs)
	proc = _make_link_proc(key, tmp_path)
	randseed = _make_link_randseed(key, tmp_path)
	randseed_done = RandSeedDone(key)
	mod = LinkLatestMod()
	mod.run(randseed=randseed, proc=proc, randseed_done=randseed_done, work_dir=tmp_path)
	assert os.readlink(tmp_path / "test.log") == str(proc.stdout_path)
	assert os.readlink(tmp_path / "test.err") == str(proc.stderr_path)
	assert os.readlink(tmp_path / "test.randseed") == randseed.randseed_path


def test_link_latest_replaces_dangling_symlink(tmp_path):
	key = "mytest"
	gone = tmp_path / "gone.log"
	(tmp_path / "test.log").symlink_to(gone)  # dangling — target never created
	gone_err = tmp_path / "gone.err"
	(tmp_path / "test.err").symlink_to(gone_err)
	gone_rs = tmp_path / "gone.randseed"
	(tmp_path / "test.randseed").symlink_to(gone_rs)
	proc = _make_link_proc(key, tmp_path)
	randseed = _make_link_randseed(key, tmp_path)
	randseed_done = RandSeedDone(key)
	mod = LinkLatestMod()
	mod.run(randseed=randseed, proc=proc, randseed_done=randseed_done, work_dir=tmp_path)
	assert os.readlink(tmp_path / "test.log") == str(proc.stdout_path)
	assert os.readlink(tmp_path / "test.err") == str(proc.stderr_path)
	assert os.readlink(tmp_path / "test.randseed") == randseed.randseed_path


def test_link_latest_two_sequential_invocations_last_writer_wins(tmp_path):
	key = "mytest"
	run1_dir = tmp_path / "run1"
	run1_dir.mkdir()
	run2_dir = tmp_path / "run2"
	run2_dir.mkdir()
	proc1 = _make_link_proc(key, run1_dir)
	rs1 = _make_link_randseed(key, run1_dir)
	proc2 = _make_link_proc(key, run2_dir)
	rs2 = _make_link_randseed(key, run2_dir)
	randseed_done = RandSeedDone(key)
	mod = LinkLatestMod()
	mod.run(randseed=rs1, proc=proc1, randseed_done=randseed_done, work_dir=tmp_path)
	mod.run(randseed=rs2, proc=proc2, randseed_done=randseed_done, work_dir=tmp_path)
	assert os.readlink(tmp_path / "test.log") == str(proc2.stdout_path)
	assert os.readlink(tmp_path / "test.err") == str(proc2.stderr_path)
	assert os.readlink(tmp_path / "test.randseed") == rs2.randseed_path


# ---------------------------------------------------------------------------
# InterpretSimMod (spec 08f)
# ---------------------------------------------------------------------------

InterpretSimMod = _mod.InterpretSimMod


def test_interpret_sim_clean_rc_zero():
	test = _make_test()
	proc = _make_proc(test.key)  # rc=0
	mod = InterpretSimMod()
	results = list(mod.run(test=test, proc=proc))
	assert len(results) == 2
	assert results[0] == ("test", test)
	assert results[1] == ("proc", proc)


def test_interpret_sim_timeout(logging_handler):
	test = _make_test()
	proc = Proc(key=test.key, rc=None, stdout_path=Path("/tmp/sim.log"), stderr_path=Path("/tmp/sim.err"))
	mod = InterpretSimMod()
	results = list(mod.run(test=test, proc=proc))
	assert len(results) == 1
	port, result = results[0]
	assert port == "timeout"
	assert result == TestResult.sim_timeout(test.key, test.get_name())
	assert logging_handler.failure is True


def test_interpret_sim_nonzero_rc():
	test = _make_test()
	proc = Proc(key=test.key, rc=1, stdout_path=Path("/tmp/sim.log"), stderr_path=Path("/tmp/sim.err"))
	mod = InterpretSimMod()
	results = list(mod.run(test=test, proc=proc))
	assert len(results) == 2
	assert results[0] == ("test", test)
	assert results[1] == ("proc", proc)

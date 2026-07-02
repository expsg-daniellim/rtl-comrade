"""Tests for modules/rtl_buddy/build.py — RunPreprocMod."""

import importlib.util
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema import RootConfig, RootRtlField, TestResult, KeyedValue, ModelConfig
from modules.rtl_buddy.schema.suite import TestConfig, TestbenchConfig

_spec = importlib.util.spec_from_file_location(
	"modules_rtl_buddy_build",
	Path(__file__).parent.parent / "rtl_buddy" / "build.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
RunPreprocMod = _mod.RunPreprocMod
WriteFilelistMod = _mod.WriteFilelistMod


def _make_tb():
	return TestbenchConfig(name="tb_top", filelist=["rtl/top.sv"])


def _make_test(name, **overrides):
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


def _make_model(key:str, name:str = "sandbox"):
	return KeyedValue(key, ModelConfig(name=name, filelist=["rtl/model.sv"]))


def _make_root_cfg():
	return RootConfig(platforms=[], rtl_builder_cfgs={}, cfg_rtl_reg=RootRtlField(path=""))


# ---------------------------------------------------------------------------
# RunPreprocMod
# ---------------------------------------------------------------------------


def test_run_preproc_no_script():
	test = _make_test("t1")  # preproc_path=None by default
	model = _make_model(test.key)
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 2
	assert results[0] == ("test", test)
	assert results[1] == ("model", model)


def test_run_preproc_mutations(tmp_path):
	script = tmp_path / "preproc.py"
	script.write_text(
		"test_cfg.set_plusarg('SEED', 42)\n"
		"test_cfg.set_plusdefine('DEBUG', 1)\n"
		"test_cfg.set_timeout(300)\n"
	)
	test = _make_test("t1", preproc_path=str(script))
	model = _make_model(test.key)
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 2
	port_t, emitted_test = results[0]
	port_m, emitted_model = results[1]
	assert port_t == "test"
	assert port_m == "model"
	assert emitted_test is test
	assert emitted_test.pa == {"SEED": 42}
	assert emitted_test.pd == {"DEBUG": 1}
	assert emitted_test.timeout == 300
	assert emitted_test.model == "sandbox"  # name string restored after exec
	assert emitted_model is model


def test_run_preproc_script_sees_resolved_model(tmp_path):
	script = tmp_path / "preproc.py"
	script.write_text(
		"test_cfg.set_plusdefine('MODEL', test_cfg.model.get_model_name())\n"
	)
	test = _make_test("t1", preproc_path=str(script))
	model = _make_model(test.key, name="sandbox")
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 2
	port_t, emitted_test = results[0]
	assert port_t == "test"
	assert emitted_test.pd == {"MODEL": "sandbox"}  # mutation from resolved model persists
	assert emitted_test.model == "sandbox"  # name string restored


def test_run_preproc_script_raises(tmp_path, logging_handler):
	script = tmp_path / "preproc.py"
	script.write_text("raise ValueError('boom')\n")
	test = _make_test("t1", preproc_path=str(script))
	model = _make_model(test.key)
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert isinstance(val, TestResult)
	assert val.result == "FAIL"
	assert logging_handler.failure is True
	assert test.model == "sandbox"  # restored synchronously before the fail yield


def test_run_preproc_script_not_found(tmp_path, logging_handler):
	test = _make_test("t1", preproc_path=str(tmp_path / "nonexistent.py"))
	model = _make_model(test.key)
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert isinstance(val, TestResult)
	assert val.result == "FAIL"
	assert logging_handler.failure is True


def test_run_preproc_script_permission_error(tmp_path, logging_handler):
	script = tmp_path / "preproc.py"
	script.write_text("test_cfg.set_plusarg('X', 1)\n")
	script.chmod(0o000)  # unreadable → PermissionError
	test = _make_test("t1", preproc_path=str(script))
	model = _make_model(test.key)
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	try:
		results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	finally:
		script.chmod(0o644)
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert isinstance(val, TestResult)
	assert val.result == "FAIL"
	assert logging_handler.failure is True


def test_run_preproc_script_read_oserror(tmp_path, logging_handler):
	preproc_dir = tmp_path / "preproc_dir"
	preproc_dir.mkdir()  # opening a directory raises IsADirectoryError (an OSError)
	test = _make_test("t1", preproc_path=str(preproc_dir))
	model = _make_model(test.key)
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert isinstance(val, TestResult)
	assert val.result == "FAIL"
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# WriteFilelistMod
# ---------------------------------------------------------------------------


def _make_model_kv(key:str, filelist=None, path=None, name="sandbox"):
	return KeyedValue(key, ModelConfig(name=name, filelist=filelist or [], path=path))


def test_write_filelist_success(tmp_path):
	"""Writes .f under work_dir, yields test then filelist; entries are work_dir-relative."""
	(tmp_path / "rtl").mkdir()
	(tmp_path / "rtl" / "model.sv").write_text("// model")
	(tmp_path / "tb").mkdir()
	(tmp_path / "tb" / "top.sv").write_text("// tb")
	test = _make_test("basic", tb=TestbenchConfig(name="tb_top", filelist=["tb/top.sv"]))
	model = _make_model_kv(test.key, filelist=["rtl/model.sv"], path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 2
	assert results[0] == ("test", test)
	port, kv = results[1]
	assert port == "filelist"
	assert kv == KeyedValue(test.key, tmp_path / "run.basic.f")
	content = (tmp_path / "run.basic.f").read_text()
	assert content.startswith("// rtl-buddy generated model filelist\n")
	assert "rtl/model.sv\n" in content
	assert "tb/top.sv\n" in content


def test_write_filelist_location_follows_work_dir(tmp_path, monkeypatch):
	"""The .f is written under work_dir regardless of the process CWD."""
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	(tmp_path / "rtl").mkdir()
	(tmp_path / "rtl" / "model.sv").write_text("// model")
	test = _make_test("loc", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, filelist=["rtl/model.sv"], path=str(tmp_path / "models.yaml"))
	list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert (tmp_path / "run.loc.f").exists()
	assert not (other / "run.loc.f").exists()


def test_write_filelist_contents_follow_work_dir(tmp_path, monkeypatch):
	"""Entry paths are relpath from work_dir, not from the process CWD."""
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	(tmp_path / "src").mkdir()
	(tmp_path / "src" / "a.sv").write_text("// a")
	test = _make_test("ct", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, filelist=["src/a.sv"], path=str(tmp_path / "models.yaml"))
	list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	content = (tmp_path / "run.ct.f").read_text()
	assert "src/a.sv\n" in content
	assert ".." not in content  # no CWD-relative escape


def test_write_filelist_tag_sanitization(tmp_path):
	"""Shell-unsafe characters in the test name are replaced with underscores in the filename."""
	test = _make_test("a/b:c", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	f_path = tmp_path / "run.a_b_c.f"
	assert f_path.exists()
	port, kv = results[1]
	assert port == "filelist"
	assert kv.value == f_path


def test_write_filelist_resolve_error(tmp_path, logging_handler):
	"""Unresolvable -F include (KeyError) or missing testbench (AttributeError) emits fail."""
	# -F include that does not exist → KeyError → filelist_resolve_error
	test1 = _make_test("re1", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model1 = _make_model_kv(test1.key, filelist=["-F nonexistent.f"], path=str(tmp_path / "models.yaml"))
	results1 = list(WriteFilelistMod().run(test=test1, model=model1, work_dir=tmp_path))
	assert len(results1) == 1
	assert results1[0][0] == "fail"
	assert isinstance(results1[0][1], TestResult)
	assert results1[0][1].result == "FAIL"
	# missing testbench (tb=None) → AttributeError → filelist_resolve_error
	test2 = _make_test("re2", tb=None)
	model2 = _make_model_kv(test2.key, path=str(tmp_path / "models.yaml"))
	results2 = list(WriteFilelistMod().run(test=test2, model=model2, work_dir=tmp_path))
	assert len(results2) == 1
	assert results2[0][0] == "fail"
	assert results2[0][1].result == "FAIL"
	assert logging_handler.failure is True


def test_write_filelist_permission_error(tmp_path, logging_handler):
	"""A read-only work_dir triggers PermissionError → filelist_permission_denied → fail."""
	work_dir = tmp_path / "readonly"
	work_dir.mkdir()
	work_dir.chmod(0o555)
	test = _make_test("perm", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, path=str(tmp_path / "models.yaml"))
	try:
		results = list(WriteFilelistMod().run(test=test, model=model, work_dir=work_dir))
	finally:
		work_dir.chmod(0o755)
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert val.result == "FAIL"
	assert logging_handler.failure is True


def test_write_filelist_dir_not_found(tmp_path, logging_handler):
	"""A non-existent work_dir parent causes FileNotFoundError → filelist_dir_not_found → fail."""
	missing = tmp_path / "nonexistent" / "subdir"
	test = _make_test("dnf", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=missing))
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert val.result == "FAIL"
	assert logging_handler.failure is True


def test_write_filelist_extract_options(tmp_path, logging_handler):
	"""Comments/blanks are skipped, +incdir+ and +libext+ options are recognised, -F is unrolled, and duplicate entries are deduplicated."""
	(tmp_path / "incdir_dir").mkdir()
	(tmp_path / "rtl").mkdir()
	(tmp_path / "rtl" / "model.sv").write_text("// model")
	(tmp_path / "rtl" / "extra.sv").write_text("// extra")
	(tmp_path / "child.f").write_text("rtl/extra.sv\n")
	filelist = [
		"// a comment",
		"",
		"+incdir+incdir_dir",
		"+libext+sv+v",
		"rtl/model.sv",
		"rtl/model.sv",  # duplicate → deduplicated
		"-F child.f",    # unrolled: pulls in rtl/extra.sv
	]
	test = _make_test("opts", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, filelist=filelist, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 2
	content = (tmp_path / "run.opts.f").read_text()
	assert "// a comment" not in content
	assert "+incdir+incdir_dir\n" in content
	assert content.count("rtl/model.sv\n") == 1  # deduplicated
	assert "rtl/extra.sv\n" in content
	libext_lines = [ln for ln in content.splitlines() if ln.startswith("+libext+")]
	assert len(libext_lines) == 1
	assert set(libext_lines[0].removeprefix("+libext+").split("+")) == {"sv", "v"}
	assert not logging_handler.failure


def test_write_filelist_process_warnings(tmp_path, logging_handler):
	"""A +incdir+ target that is not a directory, a missing source file, and a malformed option each log an error but the .f is still written."""
	(tmp_path / "rtl").mkdir()
	(tmp_path / "not_a_dir").write_text("i am a file")
	filelist = [
		"+incdir+not_a_dir",  # incdir target is a file, not a directory → warn
		"rtl/missing.sv",     # referenced source does not exist → warn
		"+incdir+",           # malformed: option prefix with no path → warn
	]
	test = _make_test("warn", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, filelist=filelist, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 2  # still writes despite the warnings
	content = (tmp_path / "run.warn.f").read_text()
	assert "+incdir+not_a_dir\n" in content
	assert "rtl/missing.sv\n" in content
	assert logging_handler.failure is True


def test_write_filelist_lower_f_fatal(tmp_path, logging_handler):
	"""A lowercase -f include is disallowed and fatals → typer.Exit."""
	test = _make_test("lowerf", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, filelist=["-f included.f"], path=str(tmp_path / "models.yaml"))
	with pytest.raises(typer.Exit):
		list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))


def test_write_filelist_is_directory(tmp_path, logging_handler):
	"""The output path already existing as a directory triggers IsADirectoryError → filelist_is_directory → fail."""
	(tmp_path / "run.isdir.f").mkdir()
	test = _make_test("isdir", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert val.result == "FAIL"
	assert logging_handler.failure is True


def test_write_filelist_write_oserror(tmp_path, logging_handler):
	"""An over-long output filename triggers a generic OSError (ENAMETOOLONG) on write → filelist_write_error → fail."""
	test = _make_test("x" * 5000, tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_model_kv(test.key, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 1
	port, val = results[0]
	assert port == "fail"
	assert val.result == "FAIL"
	assert logging_handler.failure is True

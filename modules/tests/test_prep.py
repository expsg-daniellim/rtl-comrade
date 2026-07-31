"""Tests for modules/rtl_buddy/build.py — RunPreprocMod."""

import importlib.util
import os
from pathlib import Path

import pytest
import typer

from modules.rtl_buddy.schema import RootConfig, RootRtlField, ModelConfig
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
FilelistExtractMod = _mod.FilelistExtractMod
FilelistEntry = _mod.FilelistEntry


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


def _make_model(name:str = "sandbox"):
	return ModelConfig(name=name, filelist=["rtl/model.sv"])


def _make_root_cfg():
	return RootConfig(platforms=[], rtl_builder_cfgs={}, cfg_rtl_reg=RootRtlField(path=""))


# ---------------------------------------------------------------------------
# RunPreprocMod
# ---------------------------------------------------------------------------


def test_run_preproc_no_script():
	test = _make_test("t1")  # preproc_path=None by default
	model = _make_model()
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
	model = _make_model()
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
	model = _make_model(name="sandbox")
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
	model = _make_model()
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True
	assert test.model == "sandbox"


def test_run_preproc_script_not_found(tmp_path, logging_handler):
	test = _make_test("t1", preproc_path=str(tmp_path / "nonexistent.py"))
	model = _make_model()
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file-mode enforcement, so chmod 0o000 grants no denial")
def test_run_preproc_script_permission_error(tmp_path, logging_handler):
	script = tmp_path / "preproc.py"
	script.write_text("test_cfg.set_plusarg('X', 1)\n")
	script.chmod(0o000)  # unreadable → PermissionError
	test = _make_test("t1", preproc_path=str(script))
	model = _make_model()
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	try:
		results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	finally:
		script.chmod(0o644)
	assert len(results) == 0
	assert logging_handler.failure is True


def test_run_preproc_script_read_oserror(tmp_path, logging_handler):
	preproc_dir = tmp_path / "preproc_dir"
	preproc_dir.mkdir()  # opening a directory raises IsADirectoryError (an OSError)
	test = _make_test("t1", preproc_path=str(preproc_dir))
	model = _make_model()
	root_cfg = _make_root_cfg()
	mod = RunPreprocMod()
	results = list(mod.run(test=test, model=model, root_cfg=root_cfg))
	assert len(results) == 0
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# WriteFilelistMod
# ---------------------------------------------------------------------------


def _make_filelist_model(filelist=None, path=None, name="sandbox"):
	return ModelConfig(name=name, filelist=filelist or [], path=path)


def test_write_filelist_success(tmp_path):
	"""Writes .f under work_dir, yields test then filelist; entries are work_dir-relative."""
	(tmp_path / "rtl").mkdir()
	(tmp_path / "rtl" / "model.sv").write_text("// model")
	(tmp_path / "tb").mkdir()
	(tmp_path / "tb" / "top.sv").write_text("// tb")
	test = _make_test("basic", tb=TestbenchConfig(name="tb_top", filelist=["tb/top.sv"]))
	model = _make_filelist_model(filelist=["rtl/model.sv"], path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 2
	assert results[0] == ("test", test)
	port, emitted_path = results[1]
	assert port == "filelist"
	assert emitted_path == tmp_path / "run.basic.f"
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
	model = _make_filelist_model(filelist=["rtl/model.sv"], path=str(tmp_path / "models.yaml"))
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
	model = _make_filelist_model(filelist=["src/a.sv"], path=str(tmp_path / "models.yaml"))
	list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	content = (tmp_path / "run.ct.f").read_text()
	assert "src/a.sv\n" in content
	assert ".." not in content  # no CWD-relative escape


def test_write_filelist_tag_sanitization(tmp_path):
	"""Shell-unsafe characters in the test name are replaced with underscores in the filename."""
	test = _make_test("a/b:c", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_filelist_model(path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	f_path = tmp_path / "run.a_b_c.f"
	assert f_path.exists()
	port, emitted_path = results[1]
	assert port == "filelist"
	assert emitted_path == f_path


def test_write_filelist_resolve_error(tmp_path, logging_handler):
	"""Unresolvable -F include (KeyError) or missing testbench (AttributeError) emits fail."""
	test1 = _make_test("re1", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model1 = _make_filelist_model(filelist=["-F nonexistent.f"], path=str(tmp_path / "models.yaml"))
	results1 = list(WriteFilelistMod().run(test=test1, model=model1, work_dir=tmp_path))
	assert len(results1) == 0
	test2 = _make_test("re2", tb=None)
	model2 = _make_filelist_model(path=str(tmp_path / "models.yaml"))
	results2 = list(WriteFilelistMod().run(test=test2, model=model2, work_dir=tmp_path))
	assert len(results2) == 0
	assert logging_handler.failure is True


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file-mode enforcement, so chmod 0o555 grants no denial")
def test_write_filelist_permission_error(tmp_path, logging_handler):
	"""A read-only work_dir triggers PermissionError → filelist_permission_denied."""
	work_dir = tmp_path / "readonly"
	work_dir.mkdir()
	work_dir.chmod(0o555)
	test = _make_test("perm", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_filelist_model(path=str(tmp_path / "models.yaml"))
	try:
		results = list(WriteFilelistMod().run(test=test, model=model, work_dir=work_dir))
	finally:
		work_dir.chmod(0o755)
	assert len(results) == 0
	assert logging_handler.failure is True


def test_write_filelist_dir_not_found(tmp_path, logging_handler):
	"""A non-existent work_dir parent causes FileNotFoundError → filelist_dir_not_found."""
	missing = tmp_path / "nonexistent" / "subdir"
	test = _make_test("dnf", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_filelist_model(path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=missing))
	assert len(results) == 0
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
	model = _make_filelist_model(filelist=filelist, path=str(tmp_path / "models.yaml"))
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
	model = _make_filelist_model(filelist=filelist, path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 2  # still writes despite the warnings
	content = (tmp_path / "run.warn.f").read_text()
	assert "+incdir+not_a_dir\n" in content
	assert "rtl/missing.sv\n" in content
	assert logging_handler.failure is True


def test_write_filelist_lower_f_fatal(tmp_path, logging_handler):
	"""A lowercase -f include is disallowed and fatals → typer.Exit."""
	test = _make_test("lowerf", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_filelist_model(filelist=["-f included.f"], path=str(tmp_path / "models.yaml"))
	with pytest.raises(typer.Exit):
		list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))


def test_write_filelist_is_directory(tmp_path, logging_handler):
	"""The output path already existing as a directory triggers IsADirectoryError → filelist_is_directory."""
	(tmp_path / "run.isdir.f").mkdir()
	test = _make_test("isdir", tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_filelist_model(path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_write_filelist_write_oserror(tmp_path, logging_handler):
	"""An over-long output filename triggers a generic OSError (ENAMETOOLONG) on write → filelist_write_error."""
	test = _make_test("x" * 5000, tb=TestbenchConfig(name="tb_top", filelist=[]))
	model = _make_filelist_model(path=str(tmp_path / "models.yaml"))
	results = list(WriteFilelistMod().run(test=test, model=model, work_dir=tmp_path))
	assert len(results) == 0
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# FilelistExtractMod
# ---------------------------------------------------------------------------


def test_extract_order_and_coalesced_libext():
	"""Entries preserve order, prepend base_dir, and coalesce +libext+ into one trailing entry. No relpath, no dedup."""
	filelist = ["-v lib/pkg.sv", "rtl/top.sv", "rtl/top.sv", "+incdir+inc", "+libext+sv+v", "+libext+svh"]
	model = ModelConfig(name="m", filelist=filelist)
	mod = FilelistExtractMod()
	results = list(mod.run(source=model, base_dir=Path("/design/hw")))
	assert len(results) == 1
	port, entries = results[0]
	assert port == "entries"
	assert entries[0] == FilelistEntry("/design/hw/lib/pkg.sv", "-v ")
	assert entries[1] == FilelistEntry("/design/hw/rtl/top.sv", None)
	assert entries[2] == FilelistEntry("/design/hw/rtl/top.sv", None)  # not deduped
	assert entries[3] == FilelistEntry("/design/hw/inc", "+incdir+")
	assert entries[4] == FilelistEntry("sv+v+svh", "+libext+")
	assert len(entries) == 5


def test_extract_two_base_dirs():
	"""Same record driven with two different base_dir values roots entries on each."""
	model = ModelConfig(name="m", filelist=["src/a.sv"])
	mod = FilelistExtractMod()
	e1 = list(mod.run(source=model, base_dir=Path("/dir1")))[0][1]
	e2 = list(mod.run(source=model, base_dir=Path("/dir2")))[0][1]
	assert e1[0].path == "/dir1/src/a.sv"
	assert e2[0].path == "/dir2/src/a.sv"


def test_extract_ignores_record_path_and_cwd(tmp_path, monkeypatch):
	"""Entries are rooted on base_dir, not on the record's own path or on the process CWD."""
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	model = ModelConfig(name="m", filelist=["src/a.sv"], path=str(tmp_path / "models.yaml"))
	mod = FilelistExtractMod()
	entries = list(mod.run(source=model, base_dir=Path("/explicit/base")))[0][1]
	assert entries[0].path == "/explicit/base/src/a.sv"


def test_extract_same_lines_through_each_record_type():
	"""ModelConfig, TestbenchConfig, and TestConfig wrapping that testbench all produce identical entries."""
	filelist = ["rtl/top.sv", "-v lib/pkg.sv"]
	base = Path("/design")
	tb = TestbenchConfig(name="tb", filelist=filelist)
	model = ModelConfig(name="m", filelist=filelist)
	test = _make_test("t", tb=tb)
	mod = FilelistExtractMod()
	e_model = list(mod.run(source=model, base_dir=base))[0][1]
	e_tb = list(mod.run(source=tb, base_dir=base))[0][1]
	e_test = list(mod.run(source=test, base_dir=base))[0][1]
	assert e_model == e_tb == e_test


def test_extract_f_unroll_spliced_and_rooted(tmp_path):
	"""-F with unroll=True splices included entries in order, rooted on the include file's directory."""
	sub = tmp_path / "sub"
	sub.mkdir()
	(sub / "other.f").write_text("inner.sv\n")
	model = ModelConfig(name="m", filelist=["before.sv", "-F sub/other.f", "after.sv"])
	mod = FilelistExtractMod()
	entries = list(mod.run(source=model, base_dir=tmp_path, unroll=True))[0][1]
	assert entries[0] == FilelistEntry(str(tmp_path / "before.sv"), None)
	assert entries[1] == FilelistEntry(str(sub / "inner.sv"), None)  # rooted on other.f's directory
	assert entries[2] == FilelistEntry(str(tmp_path / "after.sv"), None)


def test_extract_f_no_unroll():
	"""-F with unroll=False produces a single -F entry without recursion."""
	model = ModelConfig(name="m", filelist=["-F other.f"])
	mod = FilelistExtractMod()
	entries = list(mod.run(source=model, base_dir=Path("/design"), unroll=False))[0][1]
	assert len(entries) == 1
	assert entries[0] == FilelistEntry("/design/other.f", "-F ")


def test_extract_missing_f_include(logging_handler):
	"""Missing -F include logs filelist_resolve_error and continues with remaining lines."""
	model = ModelConfig(name="m", filelist=["-F nonexistent.f", "after.sv"])
	mod = FilelistExtractMod()
	entries = list(mod.run(source=model, base_dir=Path("/design"), unroll=True))[0][1]
	assert len(entries) == 1
	assert entries[0] == FilelistEntry("/design/after.sv", None)
	assert logging_handler.failure is True


def test_extract_lower_f_fatal(logging_handler):
	"""Lowercase -f triggers log.fatal."""
	model = ModelConfig(name="m", filelist=["-f other.f"])
	mod = FilelistExtractMod()
	with pytest.raises(typer.Exit):
		list(mod.run(source=model, base_dir=Path("/design")))


def test_extract_malformed_line(logging_handler):
	"""A malformed line (option with no path) logs filelist_malformed_line and is skipped."""
	model = ModelConfig(name="m", filelist=["+incdir+", "good.sv"])
	mod = FilelistExtractMod()
	entries = list(mod.run(source=model, base_dir=Path("/design")))[0][1]
	assert len(entries) == 1
	assert entries[0] == FilelistEntry("/design/good.sv", None)
	assert logging_handler.failure is True

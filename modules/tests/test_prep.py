"""Tests for modules/rtl_buddy/build.py — RunPreprocMod."""

import importlib.util
import os
import re
from pathlib import Path

import pytest
import typer
from serde import from_dict

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
PrioritisedMergeMod = _mod.PrioritisedMergeMod
FilelistNormaliseMod = _mod.FilelistNormaliseMod
FilelistFlattenMod = _mod.FilelistFlattenMod
FilelistStripMod = _mod.FilelistStripMod
FilelistDedupMod = _mod.FilelistDedupMod
FilelistPathMod = _mod.FilelistPathMod
BuildCompileCmdMod = _mod.BuildCompileCmdMod
filelist_extract = _mod.filelist_extract
filelist_process = _mod.filelist_process


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


def make_filelist_model(filelist=None, path=None, name="sandbox"):
	return ModelConfig(name=name, filelist=filelist or [], path=path)


def test_write_filelist_success(tmp_path):
	"""Entries with options and +libext+ render correctly; yields ("filelist", path) only."""
	entries = [
		FilelistEntry("rtl/top.sv", None),
		FilelistEntry("lib/pkg.sv", "-v "),
		FilelistEntry("inc", "+incdir+"),
		FilelistEntry("sv+v", "+libext+"),
	]
	path = tmp_path / "run.foo.f"
	test = _make_test("foo")
	results = list(WriteFilelistMod().run(entries=entries, path=path, test=test))
	assert len(results) == 1
	assert results[0] == ("filelist", path)
	content = path.read_text()
	assert content == "// rtl-buddy generated model filelist\nrtl/top.sv\n-v lib/pkg.sv\n+incdir+inc\n+libext+sv+v\n"


def test_write_filelist_parity(tmp_path):
	"""Pipeline extract x2 -> normalise -> dedup -> write reproduces the fused node's byte-for-byte .f."""
	(tmp_path / "rtl").mkdir()
	(tmp_path / "rtl" / "model.sv").write_text("// model")
	(tmp_path / "inc").mkdir()
	(tmp_path / "tb").mkdir()
	(tmp_path / "tb" / "top.sv").write_text("// tb")
	model = make_filelist_model(filelist=["rtl/model.sv", "+libext+sv", "+incdir+inc"], path=str(tmp_path / "models.yaml"))
	test = _make_test("parity", tb=TestbenchConfig(name="tb_top", filelist=["tb/top.sv", "rtl/model.sv"]))
	work_dir = tmp_path
	model_path = model.get_model_path()
	model_dir = os.path.dirname(os.path.abspath(model_path)) if model_path else str(work_dir)
	ref_entries = filelist_extract(model.get_filelist(), True, os.path.join(model_dir, "models.yaml"))
	ref_entries.extend(filelist_extract(test.get_testbench().get_filelist(), True, str(Path(work_dir) / "tests.yaml")))
	ref_lines = filelist_process(ref_entries, str(work_dir), True)
	ref_path = tmp_path / "ref.f"
	with open(ref_path, "w", encoding="utf-8") as fh:
		fh.write("// rtl-buddy generated model filelist\n")
		fh.writelines(ref_lines)
	extract = FilelistExtractMod()
	model_entries = list(extract.run(source=model, base_dir=Path(model_dir)))[0][1]
	tb_entries = list(extract.run(source=test, base_dir=work_dir))[0][1]
	combined = model_entries + tb_entries
	normalised = list(FilelistNormaliseMod().run(entries=combined, base_dir=work_dir))[0][1]
	deduped = list(FilelistDedupMod().run(entries=normalised))[0][1]
	pipe_path = tmp_path / "pipe.f"
	results = list(WriteFilelistMod().run(entries=deduped, path=pipe_path, test=test))
	assert len(results) == 1
	assert results[0] == ("filelist", pipe_path)
	assert pipe_path.read_bytes() == ref_path.read_bytes()


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file-mode enforcement, so chmod 0o555 grants no denial")
def test_write_filelist_permission_error(tmp_path, logging_handler):
	"""path into a read-only dir -> PermissionError -> filelist_permission_denied."""
	ro_dir = tmp_path / "readonly"
	ro_dir.mkdir()
	ro_dir.chmod(0o555)
	path = ro_dir / "run.foo.f"
	test = _make_test("foo")
	try:
		results = list(WriteFilelistMod().run(entries=[], path=path, test=test))
	finally:
		ro_dir.chmod(0o755)
	assert len(results) == 0
	assert logging_handler.failure is True


def test_write_filelist_dir_not_found(tmp_path, logging_handler):
	"""path with missing parent -> FileNotFoundError -> filelist_dir_not_found."""
	path = tmp_path / "nonexistent" / "subdir" / "run.foo.f"
	test = _make_test("foo")
	results = list(WriteFilelistMod().run(entries=[], path=path, test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_write_filelist_is_directory(tmp_path, logging_handler):
	"""path that is a directory -> IsADirectoryError -> filelist_is_directory."""
	dir_path = tmp_path / "run.foo.f"
	dir_path.mkdir()
	test = _make_test("foo")
	results = list(WriteFilelistMod().run(entries=[], path=dir_path, test=test))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_write_filelist_no_test(tmp_path):
	"""test omitted (filelist command) -> success still yields ("filelist", path)."""
	entries = [FilelistEntry("rtl/top.sv", None)]
	path = tmp_path / "run.f"
	results = list(WriteFilelistMod().run(entries=entries, path=path))
	assert len(results) == 1
	assert results[0] == ("filelist", path)
	assert path.read_text() == "// rtl-buddy generated model filelist\nrtl/top.sv\n"


def test_write_filelist_no_test_error(tmp_path, logging_handler):
	"""test omitted + write error -> logs with key/test_name None."""
	path = tmp_path / "nonexistent" / "run.f"
	results = list(WriteFilelistMod().run(entries=[], path=path))
	assert len(results) == 0
	assert logging_handler.failure is True


def test_write_filelist_oserror(tmp_path, logging_handler):
	"""A generic OSError (ELOOP via self-referencing symlink) reaches the catch-all handler."""
	link = tmp_path / "loop"
	link.symlink_to("loop")
	test = _make_test("foo")
	results = list(WriteFilelistMod().run(entries=[], path=link, test=test))
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


def test_extract_skips_blanks_and_comments():
	"""Blank lines, // comments, /* comments, and * lines are skipped."""
	filelist = ["", "  ", "// comment", "/* block", "* line", "rtl/top.sv"]
	model = ModelConfig(name="m", filelist=filelist)
	entries = list(FilelistExtractMod().run(source=model, base_dir=Path("/d")))[0][1]
	assert entries == [FilelistEntry("/d/rtl/top.sv", None)]


# ---------------------------------------------------------------------------
# PrioritisedMergeMod
# ---------------------------------------------------------------------------


def _merge_config(priorities):
	return from_dict(PrioritisedMergeMod.Config, {"priorities": priorities})


def test_prioritised_merge_two_ports():
	"""Two ports ordered by priority; reversed priorities reverse the output."""
	mod = PrioritisedMergeMod(config=_merge_config({"model_entries": 0, "tb_entries": 1}))
	result = mod.run(model_entries=["a", "b"], tb_entries=["c"])
	assert result == ("entries", ["a", "b", "c"])


def test_prioritised_merge_reversed_priorities():
	"""Reversed priorities produce tb before model."""
	mod = PrioritisedMergeMod(config=_merge_config({"model_entries": 1, "tb_entries": 0}))
	result = mod.run(model_entries=["a", "b"], tb_entries=["c"])
	assert result == ("entries", ["c", "a", "b"])


def test_prioritised_merge_single_port():
	"""Single port produces a correct one-element merge with no special-casing."""
	mod = PrioritisedMergeMod(config=_merge_config({"model_entries": 0}))
	result = mod.run(model_entries=["a", "b"])
	assert result == ("entries", ["a", "b"])


def test_prioritised_merge_unranked_port(logging_handler):
	"""A wired port absent from priorities triggers log.fatal."""
	mod = PrioritisedMergeMod(config=_merge_config({"model_entries": 0}))
	with pytest.raises(typer.Exit):
		mod.run(model_entries=["a"], tb_entries=["c"])


def test_prioritised_merge_equal_priority_tiebreak():
	"""Two ports with equal priority are ordered by name as deterministic tiebreak."""
	mod = PrioritisedMergeMod(config=_merge_config({"alpha_entries": 0, "beta_entries": 0}))
	result = mod.run(alpha_entries=["a"], beta_entries=["b"])
	assert result == ("entries", ["a", "b"])
	result2 = mod.run(beta_entries=["b"], alpha_entries=["a"])
	assert result2 == ("entries", ["a", "b"])


# ---------------------------------------------------------------------------
# FilelistPathMod
# ---------------------------------------------------------------------------


def test_filelist_path_simple(tmp_path):
	"""A TestConfig named foo with work_dir=tmp_path produces run.foo.f."""
	test = _make_test("foo")
	result = FilelistPathMod().run(test=test, work_dir=tmp_path)
	assert result == ("path", tmp_path / "run.foo.f")


def test_filelist_path_sanitisation():
	"""Slashes, spaces and + are replaced with _; dots, hyphens and underscores survive."""
	test = _make_test("a/b c+d.e-f_g")
	result = FilelistPathMod().run(test=test, work_dir=Path("/wd"))
	assert result == ("path", Path("/wd/run.a_b_c_d.e-f_g.f"))


def test_filelist_path_distinct_per_test(tmp_path):
	"""Two TestConfigs with different names produce distinct paths."""
	t1 = _make_test("alpha")
	t2 = _make_test("beta")
	r1 = FilelistPathMod().run(test=t1, work_dir=tmp_path)
	r2 = FilelistPathMod().run(test=t2, work_dir=tmp_path)
	assert r1[1] != r2[1]


def test_filelist_path_matches_build_compile_tag():
	"""The tag agrees with what BuildCompileCmdMod derives for obj_dir_<tag>."""
	name = "tricky/name with+stuff"
	test = _make_test(name)
	path_result = FilelistPathMod().run(test=test, work_dir=Path("/wd"))
	tag = path_result[1].stem.removeprefix("run.")  # extract tag from run.<tag>.f
	expected_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
	assert tag == expected_tag
	assert f"obj_dir_{tag}" == f"obj_dir_{expected_tag}"


def test_filelist_path_nonexistent_work_dir(tmp_path):
	"""A work_dir that does not exist still returns the joined path with no error."""
	missing = tmp_path / "does" / "not" / "exist"
	test = _make_test("t1")
	result = FilelistPathMod().run(test=test, work_dir=missing)
	assert result == ("path", missing / "run.t1.f")
	assert not missing.exists()


# ---------------------------------------------------------------------------
# FilelistNormaliseMod
# ---------------------------------------------------------------------------


def test_normalise_relativise_and_libext_passthrough(tmp_path):
	"""Entries with +incdir+, source files, and +libext+ as bare list; paths relativised against base_dir; +libext+ unchanged."""
	inc = tmp_path / "inc"
	inc.mkdir()
	src = tmp_path / "src"
	src.mkdir()
	(src / "a.sv").write_text("// a")
	entries = [
		FilelistEntry(str(inc), "+incdir+"),
		FilelistEntry(str(src / "a.sv"), None),
		FilelistEntry("sv+v", "+libext+"),
	]
	mod = FilelistNormaliseMod()
	results = list(mod.run(entries=entries, base_dir=tmp_path))
	assert len(results) == 1
	port, out = results[0]
	assert port == "entries"
	assert isinstance(out, list)
	assert out[0] == FilelistEntry("inc", "+incdir+")
	assert out[1] == FilelistEntry("src/a.sv", None)
	assert out[2] == FilelistEntry("sv+v", "+libext+")  # unchanged


def test_normalise_relpath_uses_base_dir_not_cwd(tmp_path, monkeypatch):
	"""base_dir governs relpath, not the process CWD."""
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	(tmp_path / "src").mkdir()
	(tmp_path / "src" / "a.sv").write_text("// a")
	entries = [FilelistEntry(str(tmp_path / "src" / "a.sv"), None)]
	mod = FilelistNormaliseMod()
	out = list(mod.run(entries=entries, base_dir=tmp_path))[0][1]
	assert out[0] == FilelistEntry("src/a.sv", None)
	assert ".." not in out[0].path


def test_normalise_existence_warnings(tmp_path, logging_handler):
	"""+incdir+ target not a dir and missing source path log errors; entries still emitted."""
	not_a_dir = tmp_path / "not_a_dir"
	not_a_dir.write_text("i am a file")
	entries = [
		FilelistEntry(str(not_a_dir), "+incdir+"),  # exists but is not a directory
		FilelistEntry(str(tmp_path / "missing.sv"), None),  # does not exist
	]
	mod = FilelistNormaliseMod()
	out = list(mod.run(entries=entries, base_dir=tmp_path))[0][1]
	assert len(out) == 2  # both entries still emitted
	assert out[0].option == "+incdir+"
	assert out[1].option is None
	assert logging_handler.failure is True


# ---------------------------------------------------------------------------
# FilelistFlattenMod
# ---------------------------------------------------------------------------


def test_flatten_basenames_and_options_preserved():
	"""Each non-+libext+ path becomes its basename; options are preserved."""
	entries = [
		FilelistEntry("a/b/c.sv", None),
		FilelistEntry("a/b/inc", "+incdir+"),
		FilelistEntry("x/y/pkg.sv", "-v "),
		FilelistEntry("d/e/lib", "-y "),
	]
	mod = FilelistFlattenMod()
	results = list(mod.run(entries=entries))
	assert len(results) == 1
	port, out = results[0]
	assert port == "entries"
	assert out[0] == FilelistEntry("c.sv", None)
	assert out[1] == FilelistEntry("inc", "+incdir+")
	assert out[2] == FilelistEntry("pkg.sv", "-v ")
	assert out[3] == FilelistEntry("lib", "-y ")


def test_flatten_libext_unchanged():
	"""+libext+ entry passes through without basename transformation."""
	entries = [
		FilelistEntry("a/b/c.sv", None),
		FilelistEntry("sv+v+svh", "+libext+"),
		FilelistEntry("x/y/d.sv", None),
	]
	mod = FilelistFlattenMod()
	out = list(mod.run(entries=entries))[0][1]
	assert out[0] == FilelistEntry("c.sv", None)
	assert out[1] == FilelistEntry("sv+v+svh", "+libext+")  # unchanged
	assert out[2] == FilelistEntry("d.sv", None)


# ---------------------------------------------------------------------------
# FilelistStripMod
# ---------------------------------------------------------------------------


def test_strip_drops_option():
	"""Entry with -v option → option set to None; rendered line carries no option prefix (fixes rtl_buddy no-op)."""
	entries = [FilelistEntry("path/a.sv", "-v ")]
	mod = FilelistStripMod()
	results = list(mod.run(entries=entries))
	assert len(results) == 1
	port, out = results[0]
	assert port == "entries"
	assert out[0] == FilelistEntry("path/a.sv", None)


def test_strip_libext_unchanged():
	"""+libext+ entry passes through without stripping."""
	entries = [
		FilelistEntry("path/a.sv", "-v "),
		FilelistEntry("sv+v+svh", "+libext+"),
		FilelistEntry("path/b.sv", "+incdir+"),
	]
	mod = FilelistStripMod()
	out = list(mod.run(entries=entries))[0][1]
	assert out[0] == FilelistEntry("path/a.sv", None)
	assert out[1] == FilelistEntry("sv+v+svh", "+libext+")  # unchanged
	assert out[2] == FilelistEntry("path/b.sv", None)


# ---------------------------------------------------------------------------
# FilelistDedupMod
# ---------------------------------------------------------------------------


def test_dedup_removes_duplicates_preserves_order():
	"""Repeated (path, option) entries are dropped; first occurrence and order preserved."""
	entries = [
		FilelistEntry("a.sv", None),
		FilelistEntry("b.sv", "-v "),
		FilelistEntry("a.sv", None),
		FilelistEntry("c.sv", None),
		FilelistEntry("b.sv", "-v "),
	]
	mod = FilelistDedupMod()
	results = list(mod.run(entries=entries))
	assert len(results) == 1
	port, out = results[0]
	assert port == "entries"
	assert out == [FilelistEntry("a.sv", None), FilelistEntry("b.sv", "-v "), FilelistEntry("c.sv", None)]


def test_dedup_same_path_different_option_kept():
	"""Two entries with the same path but different option are both kept."""
	entries = [
		FilelistEntry("lib/pkg.sv", None),
		FilelistEntry("lib/pkg.sv", "-v "),
	]
	mod = FilelistDedupMod()
	out = list(mod.run(entries=entries))[0][1]
	assert len(out) == 2
	assert out[0] == FilelistEntry("lib/pkg.sv", None)
	assert out[1] == FilelistEntry("lib/pkg.sv", "-v ")


def test_dedup_after_flatten_catches_basename_collision():
	"""After flatten, two entries sharing a basename collide and dedup catches the duplicate."""
	entries = [
		FilelistEntry("a/b/top.sv", None),
		FilelistEntry("x/y/top.sv", None),
	]
	flat = list(FilelistFlattenMod().run(entries=entries))[0][1]
	assert flat[0] == FilelistEntry("top.sv", None)
	assert flat[1] == FilelistEntry("top.sv", None)  # now duplicates
	out = list(FilelistDedupMod().run(entries=flat))[0][1]
	assert out == [FilelistEntry("top.sv", None)]


# ---------------------------------------------------------------------------
# filelist_extract (standalone function)
# ---------------------------------------------------------------------------


def test_filelist_extract_blanks_and_comments():
	"""Blank lines, // comments, /* comments, and * lines are skipped."""
	lines = ["\n", "  \n", "// comment\n", "/* block\n", "* line\n", "a.sv\n"]
	result = filelist_extract(lines, False, "/base/file.f")
	assert result == [("/base/a.sv", None)]


def test_filelist_extract_malformed(logging_handler):
	"""Option with no path is skipped with an error."""
	lines = ["+incdir+\n", "good.sv\n"]
	result = filelist_extract(lines, False, "/base/file.f")
	assert result == [("/base/good.sv", None)]
	assert logging_handler.failure is True


def test_filelist_extract_dash_v():
	"""-v option is parsed into group(1), yielding ("-v ", path) tuples."""
	result = filelist_extract(["-v lib/pkg.sv\n"], False, "/base/file.f")
	assert result == [("/base/lib/pkg.sv", "-v ")]


def test_filelist_extract_lower_f_fatal(logging_handler):
	"""Lowercase -f triggers log.fatal."""
	with pytest.raises(typer.Exit):
		filelist_extract(["-f other.f\n"], False, "/base/file.f")


def test_filelist_extract_upper_f_unroll(tmp_path):
	"""-F with unroll=True opens the include and splices its entries."""
	sub = tmp_path / "sub"
	sub.mkdir()
	(sub / "inner.f").write_text("inner.sv\n")
	fpath = str(tmp_path / "outer.f")
	result = filelist_extract(["-F sub/inner.f\n", "after.sv\n"], True, fpath)
	assert result == [(str(sub / "inner.sv"), None), (str(tmp_path / "after.sv"), None)]


def test_filelist_extract_upper_f_missing(tmp_path):
	"""-F with unroll=True raises KeyError when the include file is missing."""
	fpath = str(tmp_path / "outer.f")
	with pytest.raises(KeyError, match="F-include error"):
		filelist_extract(["-F missing.f\n"], True, fpath)


# ---------------------------------------------------------------------------
# filelist_process (standalone function)
# ---------------------------------------------------------------------------


def test_filelist_process_incdir_not_a_dir(tmp_path, logging_handler):
	"""+incdir+ target that is not a directory logs filelist_incdir_not_a_dir."""
	not_a_dir = tmp_path / "not_a_dir"
	not_a_dir.write_text("file")
	result = filelist_process([(str(not_a_dir), "+incdir+")], str(tmp_path), False)
	assert len(result) == 1
	assert logging_handler.failure is True


def test_filelist_process_file_not_found(tmp_path, logging_handler):
	"""Missing source file logs filelist_file_not_found."""
	result = filelist_process([(str(tmp_path / "missing.sv"), None)], str(tmp_path), False)
	assert len(result) == 1
	assert logging_handler.failure is True

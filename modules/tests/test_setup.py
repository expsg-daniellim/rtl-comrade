"""Tests for modules/rtl_buddy/setup.py using the module testing harness."""

import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.testing import run_module_scenario
from modules.rtl_buddy.schema import PlatformConfig, RootConfig, RootRtlField, RtlBuilderConfig, SeedMode
from modules.rtl_buddy.schema.suite import SuiteConfig, TestConfig, TestbenchConfig

_spec = importlib.util.spec_from_file_location(
	"modules_rtl_buddy_setup",
	Path(__file__).parent.parent / "rtl_buddy" / "setup.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
DiscoverConfigFileMod = _mod.DiscoverConfigFileMod
PrependCwdPathMod = _mod.PrependCwdPathMod
ParseRootConfigMod = _mod.ParseRootConfigMod
SelectPlatformMod = _mod.SelectPlatformMod
ResolveBuilderMod = _mod.ResolveBuilderMod
WorkDirMod = _mod.WorkDirMod
EnsureLogsDirMod = _mod.EnsureLogsDirMod
ParseSuiteConfigMod = _mod.ParseSuiteConfigMod
DeriveSeedModeMod = _mod.DeriveSeedModeMod

_FIXTURE = Path(__file__).parent / "fixtures" / "root_config.yaml"
_SUITE_FIXTURE = Path(__file__).parent / "fixtures" / "verif" / "sandbox" / "tests.yaml"


# ---------------------------------------------------------------------------
# DiscoverConfigFileMod
# ---------------------------------------------------------------------------


async def test_discover_found_at_cwd(tmp_path, monkeypatch):
	f = tmp_path / "root_config.yaml"
	f.write_text("")
	monkeypatch.chdir(tmp_path)
	await run_module_scenario(
		DiscoverConfigFileMod,
		input_sequence=[{}],
		expected_emissions={"default": [f]},
		config=DiscoverConfigFileMod.Config(filename="root_config.yaml"),
	)


async def test_discover_found_n_levels_up(tmp_path, monkeypatch):
	f = tmp_path / "root_config.yaml"
	f.write_text("")
	cwd = tmp_path / "a" / "b"
	cwd.mkdir(parents=True)
	monkeypatch.chdir(cwd)
	await run_module_scenario(
		DiscoverConfigFileMod,
		input_sequence=[{}],
		expected_emissions={"default": [f]},
		config=DiscoverConfigFileMod.Config(filename="root_config.yaml"),
	)


async def test_discover_not_found_depth_limit(tmp_path, monkeypatch, logging_handler):
	f = tmp_path / "root_config.yaml"
	f.write_text("")
	cwd = tmp_path / "a" / "b" / "c"
	cwd.mkdir(parents=True)
	monkeypatch.chdir(cwd)
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			DiscoverConfigFileMod,
			input_sequence=[{}],
			expected_emissions={},
			config=DiscoverConfigFileMod.Config(filename="root_config.yaml", max_levels=2),
		)


async def test_discover_permission_error(tmp_path, monkeypatch, logging_handler):
	monkeypatch.chdir(tmp_path)

	def raise_perm_error(self):
		raise PermissionError("Permission denied")

	monkeypatch.setattr(Path, "is_file", raise_perm_error)
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			DiscoverConfigFileMod,
			input_sequence=[{}],
			expected_emissions={},
			config=DiscoverConfigFileMod.Config(filename="root_config.yaml"),
		)


async def test_discover_reaches_filesystem_root(tmp_path, monkeypatch, logging_handler):
	monkeypatch.chdir(tmp_path)
	monkeypatch.setattr(Path, "is_file", lambda self: False)  # never found → ascend until d == d.parent (root)
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			DiscoverConfigFileMod,
			input_sequence=[{}],
			expected_emissions={},
			config=DiscoverConfigFileMod.Config(filename="root_config.yaml", max_levels=50),
		)


# ---------------------------------------------------------------------------
# PrependCwdPathMod
# ---------------------------------------------------------------------------


async def test_prepend_path_without_dot(monkeypatch):
	monkeypatch.setenv("PATH", "/usr/bin:/bin")
	await run_module_scenario(
		PrependCwdPathMod,
		input_sequence=[{}],
		expected_emissions={"default": [True]},
	)
	assert os.environ["PATH"] == "." + os.pathsep + "/usr/bin:/bin"


async def test_prepend_path_already_at_head(monkeypatch):
	monkeypatch.setenv("PATH", ".:/usr/bin:/bin")
	await run_module_scenario(
		PrependCwdPathMod,
		input_sequence=[{}],
		expected_emissions={"default": [True]},
	)
	assert os.environ["PATH"] == ".:/usr/bin:/bin"


async def test_prepend_path_dot_in_middle(monkeypatch):
	monkeypatch.setenv("PATH", "/usr/bin:.:/bin")
	await run_module_scenario(
		PrependCwdPathMod,
		input_sequence=[{}],
		expected_emissions={"default": [True]},
	)
	assert os.environ["PATH"] == "/usr/bin:.:/bin"


async def test_prepend_path_unset(monkeypatch):
	monkeypatch.delenv("PATH", raising=False)
	await run_module_scenario(
		PrependCwdPathMod,
		input_sequence=[{}],
		expected_emissions={"default": [True]},
	)
	assert os.environ["PATH"] == "."


async def test_prepend_path_end_to_end(tmp_path, monkeypatch):
	script = tmp_path / "local_tool"
	script.write_text("#!/bin/sh\nexit 0\n")
	script.chmod(0o755)
	monkeypatch.chdir(tmp_path)
	monkeypatch.setenv("PATH", "/usr/bin:/bin")
	with pytest.raises(FileNotFoundError):
		subprocess.run(["local_tool"], check=False)
	await run_module_scenario(
		PrependCwdPathMod,
		input_sequence=[{}],
		expected_emissions={"default": [True]},
	)
	result = subprocess.run(["local_tool"], check=False)
	assert result.returncode == 0


# ---------------------------------------------------------------------------
# ParseRootConfigMod
# ---------------------------------------------------------------------------


def test_parse_root_config_valid():
	mod = ParseRootConfigMod()
	result = mod.run(path=_FIXTURE)
	assert result is not None
	port, root_cfg = result
	assert port == "default"
	assert isinstance(root_cfg, RootConfig)
	assert root_cfg.cfg_rtl_reg.path == "design/regression.yaml"
	assert len(root_cfg.platforms) == 2
	assert root_cfg.platforms[0].os == "osx"
	assert root_cfg.platforms[1].os == "server"
	assert set(root_cfg.rtl_builder_cfgs.keys()) == {"verilator", "vcs"}
	assert root_cfg.rtl_builder_cfgs["verilator"].get_name() == "verilator"
	assert root_cfg.rtl_builder_cfgs["vcs"].get_name() == "vcs"


def test_parse_root_config_verible_keys_ignored():
	mod = ParseRootConfigMod()
	result = mod.run(path=_FIXTURE)
	assert result is not None
	_, root_cfg = result
	assert isinstance(root_cfg, RootConfig)
	assert root_cfg.cfg_rtl_reg.path == "design/regression.yaml"
	assert set(root_cfg.rtl_builder_cfgs.keys()) == {"verilator", "vcs"}


def test_parse_root_config_nonexistent(logging_handler):
	mod = ParseRootConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(path=Path("/nonexistent/path/root_config.yaml"))


def test_parse_root_config_is_directory(tmp_path, logging_handler):
	mod = ParseRootConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(path=tmp_path)


def test_parse_root_config_non_utf8(tmp_path, logging_handler):
	bad = tmp_path / "root_config.yaml"
	bad.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
	mod = ParseRootConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(path=bad)


def test_parse_root_config_malformed_yaml(tmp_path, logging_handler):
	bad = tmp_path / "root_config.yaml"
	bad.write_text("key: [\nunot closed")
	mod = ParseRootConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(path=bad)


def test_parse_root_config_schema_mismatch(tmp_path, logging_handler):
	bad = tmp_path / "root_config.yaml"
	bad.write_text("rtl-buddy-filetype: wrong_type\ncfg-rtl-reg:\n  reg-cfg-path: x\n")
	mod = ParseRootConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(path=bad)


# ---------------------------------------------------------------------------
# SelectPlatformMod
# ---------------------------------------------------------------------------


class _FakeProc:
	def __init__(self, stdout):
		self.stdout = stdout


def _fake_uname(uname_str):
	return lambda *a, **kw: _FakeProc(uname_str)


def _root_cfg(*uname_lists):
	platforms = [
		PlatformConfig(os=f"os{i}", unames=list(ul), builder=f"b{i}")
		for i, ul in enumerate(uname_lists)
	]
	return RootConfig(platforms=platforms, rtl_builder_cfgs={}, cfg_rtl_reg=RootRtlField(path="x"))


def test_select_platform_first_match(monkeypatch, logging_handler):
	root_cfg = _root_cfg(["Darwin"], ["Linux"])
	monkeypatch.setattr(subprocess, "run", _fake_uname("Darwin"))
	mod = SelectPlatformMod()
	port, cfg = mod.run(root_cfg=root_cfg)
	assert port == "default"
	assert cfg is root_cfg.platforms[0]


def test_select_platform_later_match(monkeypatch, logging_handler):
	root_cfg = _root_cfg(["Darwin"], ["Linux"])
	monkeypatch.setattr(subprocess, "run", _fake_uname("Linux"))
	mod = SelectPlatformMod()
	port, cfg = mod.run(root_cfg=root_cfg)
	assert port == "default"
	assert cfg is root_cfg.platforms[1]


def test_select_platform_first_wins_overlap(monkeypatch, logging_handler):
	root_cfg = _root_cfg(["Darwin"], ["Darwin", "Linux"])
	monkeypatch.setattr(subprocess, "run", _fake_uname("Darwin"))
	mod = SelectPlatformMod()
	port, cfg = mod.run(root_cfg=root_cfg)
	assert port == "default"
	assert cfg is root_cfg.platforms[0]


def test_select_platform_no_match(monkeypatch, logging_handler):
	root_cfg = _root_cfg(["Darwin"], ["Linux"])
	monkeypatch.setattr(subprocess, "run", _fake_uname("IRIX"))
	mod = SelectPlatformMod()
	with pytest.raises(typer.Exit):
		mod.run(root_cfg=root_cfg)


def test_select_platform_uname_not_found(monkeypatch, logging_handler):
	root_cfg = _root_cfg(["Darwin"])
	def raise_fnf(*a, **kw):
		raise FileNotFoundError("no uname binary")
	monkeypatch.setattr(subprocess, "run", raise_fnf)
	mod = SelectPlatformMod()
	with pytest.raises(typer.Exit):
		mod.run(root_cfg=root_cfg)


def test_select_platform_uname_failed(monkeypatch, logging_handler):
	root_cfg = _root_cfg(["Darwin"])
	def raise_called_process(*a, **kw):
		raise subprocess.CalledProcessError(1, ["uname"])
	monkeypatch.setattr(subprocess, "run", raise_called_process)
	mod = SelectPlatformMod()
	with pytest.raises(typer.Exit):
		mod.run(root_cfg=root_cfg)


# ---------------------------------------------------------------------------
# ResolveBuilderMod
# ---------------------------------------------------------------------------


def _builder_cfg(name):
	return RtlBuilderConfig(name=name, exe="sim", simv="simv", sim_rand_seed=42, sim_rand_prefix="+seed=", opts={})


def _resolve_root_cfg(*names):
	return RootConfig(platforms=[], rtl_builder_cfgs={n: _builder_cfg(n) for n in names}, cfg_rtl_reg=RootRtlField(path="x"))


def _platform_cfg(builder):
	return PlatformConfig(os="osx", unames=["Darwin"], builder=builder)


def test_resolve_builder_no_override_uses_platform():
	root_cfg = _resolve_root_cfg("verilator", "vcs")
	platform_cfg = _platform_cfg("verilator")
	mod = ResolveBuilderMod()
	port, cfg = mod.run(root_cfg=root_cfg, platform_cfg=platform_cfg, builder="")
	assert port == "default"
	assert cfg is root_cfg.rtl_builder_cfgs["verilator"]


def test_resolve_builder_override_wins():
	root_cfg = _resolve_root_cfg("verilator", "vcs")
	platform_cfg = _platform_cfg("verilator")
	mod = ResolveBuilderMod()
	port, cfg = mod.run(root_cfg=root_cfg, platform_cfg=platform_cfg, builder="vcs")
	assert port == "default"
	assert cfg is root_cfg.rtl_builder_cfgs["vcs"]


def test_resolve_builder_unknown_override(logging_handler):
	root_cfg = _resolve_root_cfg("verilator")
	platform_cfg = _platform_cfg("verilator")
	mod = ResolveBuilderMod()
	with pytest.raises(typer.Exit):
		mod.run(root_cfg=root_cfg, platform_cfg=platform_cfg, builder="unknown")


def test_resolve_builder_platform_none_no_override(logging_handler):
	root_cfg = _resolve_root_cfg("verilator")
	platform_cfg = _platform_cfg(None)
	mod = ResolveBuilderMod()
	with pytest.raises(typer.Exit):
		mod.run(root_cfg=root_cfg, platform_cfg=platform_cfg, builder="")


def test_resolve_builder_empty_dict(logging_handler):
	root_cfg = _resolve_root_cfg()
	platform_cfg = _platform_cfg("verilator")
	mod = ResolveBuilderMod()
	with pytest.raises(typer.Exit):
		mod.run(root_cfg=root_cfg, platform_cfg=platform_cfg, builder="")


# ---------------------------------------------------------------------------
# WorkDirMod
# ---------------------------------------------------------------------------


async def test_work_dir_known_cwd(tmp_path, monkeypatch):
	monkeypatch.chdir(tmp_path)
	await run_module_scenario(
		WorkDirMod,
		input_sequence=[{}],
		expected_emissions={"default": [tmp_path.resolve()]},
	)


async def test_work_dir_changes_with_chdir(tmp_path, monkeypatch):
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	await run_module_scenario(
		WorkDirMod,
		input_sequence=[{}],
		expected_emissions={"default": [other.resolve()]},
	)


async def test_work_dir_resolves_symlink(tmp_path, monkeypatch):
	real = tmp_path / "real"
	real.mkdir()
	link = tmp_path / "link"
	link.symlink_to(real)
	monkeypatch.chdir(link)
	await run_module_scenario(
		WorkDirMod,
		input_sequence=[{}],
		expected_emissions={"default": [real.resolve()]},
	)


# ---------------------------------------------------------------------------
# EnsureLogsDirMod
# ---------------------------------------------------------------------------


def test_ensure_logs_dir_creates_default(tmp_path):
	mod = EnsureLogsDirMod()
	port, path = mod.run(work_dir=tmp_path)
	assert port == "logs_dir"
	assert path == tmp_path / "logs"
	assert (tmp_path / "logs").is_dir()


def test_ensure_logs_dir_idempotent(tmp_path):
	(tmp_path / "logs").mkdir()
	mod = EnsureLogsDirMod()
	port, path = mod.run(work_dir=tmp_path)
	assert port == "logs_dir"
	assert path == tmp_path / "logs"
	assert (tmp_path / "logs").is_dir()


def test_ensure_logs_dir_nested(tmp_path):
	mod = EnsureLogsDirMod()
	port, path = mod.run(work_dir=tmp_path, logs_dir="build/logs")
	assert port == "logs_dir"
	assert path == tmp_path / "build" / "logs"
	assert (tmp_path / "build" / "logs").is_dir()


def test_ensure_logs_dir_roots_on_work_dir_not_cwd(tmp_path, monkeypatch):
	other = tmp_path / "other"
	other.mkdir()
	monkeypatch.chdir(other)
	mod = EnsureLogsDirMod()
	port, path = mod.run(work_dir=tmp_path)
	assert port == "logs_dir"
	assert path == tmp_path / "logs"
	assert (tmp_path / "logs").is_dir()
	assert not (other / "logs").exists()


def test_ensure_logs_dir_permission_error(tmp_path, monkeypatch, logging_handler):
	mod = EnsureLogsDirMod()
	with patch("pathlib.Path.mkdir", side_effect=PermissionError("denied")):
		with pytest.raises(typer.Exit):
			mod.run(work_dir=tmp_path)


# ---------------------------------------------------------------------------
# ParseSuiteConfigMod
# ---------------------------------------------------------------------------

_MINIMAL_SUITE_YAML = """\
rtl-buddy-filetype: test_config
testbenches:
  - name: "tb"
    filelist: ["tb.sv"]
tests:
  - name: "t"
    desc: "d"
    model: "m"
    model_path: "models.yaml"
    testbench: "tb"
"""


def test_parse_suite_config_happy_path():
	mod = ParseSuiteConfigMod()
	result = mod.run(test_config=str(_SUITE_FIXTURE))
	assert result is not None
	port, suite_cfg = result
	assert port == "default"
	assert isinstance(suite_cfg, SuiteConfig)
	assert suite_cfg.path == _SUITE_FIXTURE.resolve()
	assert "basic" in suite_cfg.tests
	for test in suite_cfg.tests.values():
		assert isinstance(test, TestConfig)
		assert isinstance(test.tb, TestbenchConfig)
		assert test.key == test.name
		assert test.suite_dir == _SUITE_FIXTURE.resolve().parent


def test_parse_suite_config_relative_cwd(tmp_path, monkeypatch):
	yaml_path = tmp_path / "tests.yaml"
	yaml_path.write_text(_MINIMAL_SUITE_YAML)
	monkeypatch.chdir(tmp_path)
	mod = ParseSuiteConfigMod()
	result = mod.run(test_config="tests.yaml")
	assert result is not None
	port, suite_cfg = result
	assert port == "default"
	assert suite_cfg.path == yaml_path.resolve()
	assert suite_cfg.tests["t"].suite_dir == yaml_path.resolve().parent


def test_parse_suite_config_relative_subdir(tmp_path, monkeypatch):
	sub = tmp_path / "sub"
	sub.mkdir()
	yaml_path = sub / "tests.yaml"
	yaml_path.write_text(_MINIMAL_SUITE_YAML)
	monkeypatch.chdir(tmp_path)
	mod = ParseSuiteConfigMod()
	result = mod.run(test_config="sub/tests.yaml")
	assert result is not None
	port, suite_cfg = result
	assert port == "default"
	assert suite_cfg.path == yaml_path.resolve()
	assert suite_cfg.tests["t"].suite_dir == sub.resolve()


def test_parse_suite_config_round_trip():
	mod = ParseSuiteConfigMod()
	_, suite_cfg = mod.run(test_config=str(_SUITE_FIXTURE))
	basic = suite_cfg.tests["basic"]
	assert basic.name == "basic"
	assert basic.desc == "basic testcase"
	assert basic.tb.name == "tb_top"
	assert basic.reglvl == 0
	assert basic.pa == {"a": "8", "b": None, "lvm_verbosity": 2}
	assert basic.pd is None
	assert basic.uvm is None
	assert basic.preproc_path is None
	assert basic.postproc_path is None
	assert basic.sweep_path is None
	assert basic.timeout is None
	assert isinstance(basic.model, str)
	assert basic.model == "test_module"
	assert basic.model_path == "../../design/sandbox/models.yaml"
	sim_timeout_test = suite_cfg.tests["sim_timeout"]
	assert sim_timeout_test.timeout == 5


def test_parse_suite_config_yaml_renames(tmp_path):
	yaml_text = """\
rtl-buddy-filetype: test_config
testbenches:
  - name: "tb"
    filelist: ["tb.sv"]
tests:
  - name: "t"
    desc: "desc"
    model: "m"
    model_path: "models.yaml"
    testbench: "tb"
    plusargs:
      A: "1"
    plusdefines:
      B: "2"
    preproc:
      path: pre.py
    postproc:
      path: post.py
    sweep:
      path: sweep.py
    sim_timeout: 99
    reglvl: 7
"""
	p = tmp_path / "tests.yaml"
	p.write_text(yaml_text)
	mod = ParseSuiteConfigMod()
	_, suite_cfg = mod.run(test_config=str(p))
	t = suite_cfg.tests["t"]
	assert t.tb.name == "tb"
	assert t.pa == {"A": "1"}
	assert t.pd == {"B": "2"}
	assert t.preproc_path == "pre.py"
	assert t.postproc_path == "post.py"
	assert t.sweep_path == "sweep.py"
	assert t.timeout == 99
	assert t.reglvl == 7


def test_parse_suite_config_preproc_mapping(tmp_path):
	yaml_text = """\
rtl-buddy-filetype: test_config
testbenches:
  - name: "tb"
    filelist: []
tests:
  - name: "t"
    desc: "d"
    model: "m"
    model_path: "models.yaml"
    testbench: "tb"
    preproc:
      path: foo.py
"""
	p = tmp_path / "tests.yaml"
	p.write_text(yaml_text)
	mod = ParseSuiteConfigMod()
	_, suite_cfg = mod.run(test_config=str(p))
	assert suite_cfg.tests["t"].preproc_path == "foo.py"


def test_parse_suite_config_preproc_omitted(tmp_path):
	p = tmp_path / "tests.yaml"
	p.write_text(_MINIMAL_SUITE_YAML)
	mod = ParseSuiteConfigMod()
	_, suite_cfg = mod.run(test_config=str(p))
	assert suite_cfg.tests["t"].preproc_path is None


def test_parse_suite_config_preproc_null(tmp_path):
	yaml_text = """\
rtl-buddy-filetype: test_config
testbenches:
  - name: "tb"
    filelist: []
tests:
  - name: "t"
    desc: "d"
    model: "m"
    model_path: "models.yaml"
    testbench: "tb"
    preproc: null
"""
	p = tmp_path / "tests.yaml"
	p.write_text(yaml_text)
	mod = ParseSuiteConfigMod()
	_, suite_cfg = mod.run(test_config=str(p))
	assert suite_cfg.tests["t"].preproc_path is None


def test_parse_suite_config_lazy_model():
	mod = ParseSuiteConfigMod()
	_, suite_cfg = mod.run(test_config=str(_SUITE_FIXTURE))
	for test in suite_cfg.tests.values():
		assert isinstance(test.model, str)
		assert len(test.model) > 0
		assert isinstance(test.model_path, str)
		assert test.suite_dir == _SUITE_FIXTURE.resolve().parent


def test_parse_suite_config_not_found(tmp_path, logging_handler):
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(tmp_path / "nonexistent.yaml"))


def test_parse_suite_config_is_directory(tmp_path, logging_handler):
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(tmp_path))


def test_parse_suite_config_invalid_unicode(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_bytes(b"\xff\xfe invalid utf-8 \x80\x81")
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(bad))


def test_parse_suite_config_permission_denied(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_text("rtl-buddy-filetype: test_config\ntestbenches: []\ntests: []\n")
	bad.chmod(0o000)
	mod = ParseSuiteConfigMod()
	try:
		with pytest.raises(typer.Exit):
			mod.run(test_config=str(bad))
	finally:
		bad.chmod(0o644)


def test_parse_suite_config_os_error(tmp_path, logging_handler):
	too_long = tmp_path / ("x" * 5000 + ".yaml")  # ENAMETOOLONG on read → generic OSError
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(too_long))


def test_parse_suite_config_yaml_unreadable(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_bytes(b"\x00")  # valid UTF-8 but a non-printable char → yaml ReaderError
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(bad))


def test_parse_suite_config_yaml_invalid(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_text("key: [\nnot closed")
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(bad))


def test_parse_suite_config_serde_error(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_text("rtl-buddy-filetype: wrong_type\ntestbenches: []\ntests: []\n")
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(bad))


def test_parse_suite_config_invalid_uvm_config(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_text("""\
rtl-buddy-filetype: test_config
testbenches:
  - name: "tb"
    filelist: []
tests:
  - name: "t"
    desc: "d"
    model: "m"
    model_path: "models.yaml"
    testbench: "tb"
    uvm:
      max_warns: -1
""")
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(bad))


def test_parse_suite_config_unknown_testbench(tmp_path, logging_handler):
	bad = tmp_path / "tests.yaml"
	bad.write_text("""\
rtl-buddy-filetype: test_config
testbenches:
  - name: "tb_a"
    filelist: []
tests:
  - name: "t"
    desc: "d"
    model: "m"
    model_path: "models.yaml"
    testbench: "tb_nonexistent"
""")
	mod = ParseSuiteConfigMod()
	with pytest.raises(typer.Exit):
		mod.run(test_config=str(bad))


# ---------------------------------------------------------------------------
# DeriveSeedModeMod
# ---------------------------------------------------------------------------


def test_derive_seed_mode_rnd_new_wins_over_rnd_last():
	mod = DeriveSeedModeMod()
	assert mod.run(rnd_new=True, rnd_last=True) == ("default", SeedMode.NEW)


def test_derive_seed_mode_rnd_new_only():
	mod = DeriveSeedModeMod()
	assert mod.run(rnd_new=True, rnd_last=False) == ("default", SeedMode.NEW)


def test_derive_seed_mode_rnd_last_only():
	mod = DeriveSeedModeMod()
	assert mod.run(rnd_new=False, rnd_last=True) == ("default", SeedMode.REPLAY)


def test_derive_seed_mode_neither():
	mod = DeriveSeedModeMod()
	assert mod.run(rnd_new=False, rnd_last=False) == ("default", SeedMode.DEFAULT)


def test_derive_seed_mode_defaults():
	mod = DeriveSeedModeMod()
	assert mod.run() == ("default", SeedMode.DEFAULT)

"""Tests for modules/rtl_buddy/setup.py using the module testing harness."""

import importlib.util
import os
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.testing import run_module_scenario
from modules.rtl_buddy.schema import PlatformConfig, RootConfig, RootRtlField

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

_FIXTURE = Path(__file__).parent.parent.parent / "rtl-buddy-proj-template" / "root_config.yaml"


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
        subprocess.run(["local_tool"])
    await run_module_scenario(
        PrependCwdPathMod,
        input_sequence=[{}],
        expected_emissions={"default": [True]},
    )
    result = subprocess.run(["local_tool"])
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

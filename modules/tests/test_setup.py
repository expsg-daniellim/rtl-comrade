"""Tests for modules/rtl_buddy/setup.py using the module testing harness."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.testing import run_module_scenario

_spec = importlib.util.spec_from_file_location(
    "modules_rtl_buddy_setup",
    Path(__file__).parent.parent / "rtl_buddy" / "setup.py",
)
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
DiscoverConfigFileMod = _mod.DiscoverConfigFileMod


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

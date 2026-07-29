"""Tests for modules/rtl_buddy/schema/ — spec 01 acceptance criteria."""

import dataclasses
from pathlib import Path

import pytest
from serde.yaml import from_yaml

from modules.rtl_buddy.schema import (
	RootConfig, RootRtlField, PlatformConfig,
	SeedMode, RunDepth,
	KeyedValue, Command, Proc, RandSeed, RandSeedDone,
)


# ---------------------------------------------------------------------------
# RootConfig round-trip
# ---------------------------------------------------------------------------


def test_root_config_round_trips_members():
	rtl = RootRtlField(path="/some/path")
	plat = PlatformConfig(os="linux", unames=["Linux"], builder="vcs")
	cfg = RootConfig(platforms=[plat], rtl_builder_cfgs={"vcs": "placeholder"}, cfg_rtl_reg=rtl)
	assert cfg.platforms == [plat]
	assert cfg.rtl_builder_cfgs == {"vcs": "placeholder"}
	assert cfg.cfg_rtl_reg is rtl


# ---------------------------------------------------------------------------
# RootRtlField deserialises from YAML with rename
# ---------------------------------------------------------------------------


def test_root_rtl_field_from_yaml():
	yaml_str = "reg-cfg-path: regs/top.yaml\n"
	obj = from_yaml(RootRtlField, yaml_str)
	assert obj.path == "regs/top.yaml"


# ---------------------------------------------------------------------------
# PlatformConfig deserialises from YAML (verible key ignored)
# ---------------------------------------------------------------------------


def test_platform_config_from_yaml():
	yaml_str = (
		"os: linux\n"
		"unames:\n"
		"  - Linux\n"
		"builder: vcs\n"
	)
	obj = from_yaml(PlatformConfig, yaml_str)
	assert obj.os == "linux"
	assert obj.unames == ["Linux"]
	assert obj.builder == "vcs"


def test_platform_config_ignores_verible_key():
	yaml_str = (
		"os: linux\n"
		"unames:\n"
		"  - Linux\n"
		"builder: vcs\n"
		"verible: some_value\n"
	)
	obj = from_yaml(PlatformConfig, yaml_str)
	assert obj.os == "linux"
	assert not hasattr(obj, "verible")


def test_platform_config_builder_none():
	yaml_str = (
		"os: macos\n"
		"unames:\n"
		"  - Darwin\n"
		"builder: null\n"
	)
	obj = from_yaml(PlatformConfig, yaml_str)
	assert obj.builder is None


# ---------------------------------------------------------------------------
# SeedMode enum
# ---------------------------------------------------------------------------


def test_seed_mode_members():
	assert SeedMode.NEW.value == "new"
	assert SeedMode.REPLAY.value == "replay"
	assert SeedMode.DEFAULT.value == "default"


# ---------------------------------------------------------------------------
# RunDepth enum — declaration order and values
# ---------------------------------------------------------------------------


def test_run_depth_values():
	assert RunDepth.PRE.value == "pre"
	assert RunDepth.COMP.value == "comp"
	assert RunDepth.SIM.value == "sim"
	assert RunDepth.POST.value == "post"


def test_run_depth_order():
	assert [d.value for d in RunDepth] == ["pre", "comp", "sim", "post"]


# ---------------------------------------------------------------------------
# Payload dataclasses — frozen, expose key
# ---------------------------------------------------------------------------


def test_keyed_value_frozen_and_keyed():
	kv = KeyedValue(key="k1", value=42)
	assert kv.key == "k1"
	assert kv.value == 42
	with pytest.raises(dataclasses.FrozenInstanceError):
		kv.key = "other"


def test_keyed_value_generic():
	kv_int:KeyedValue[int] = KeyedValue(key="a", value=10)
	kv_str:KeyedValue[str] = KeyedValue(key="b", value="hello")
	assert kv_int.value == 10
	assert kv_str.value == "hello"


def test_keyed_value_mutation_through_envelope():
	"""Frozen envelope does not block mutating the wrapped mutable object."""
	inner = {"x": 1}
	kv = KeyedValue(key="k", value=inner)
	kv.value["x"] = 99
	assert kv.value["x"] == 99


def test_command_frozen_and_keyed():
	c = Command(key="k", argv=["vcs", "-f", "top.f"], stdout_path=Path("/tmp/out"), stderr_path=Path("/tmp/err"))
	assert c.key == "k"
	assert c.argv == ["vcs", "-f", "top.f"]
	with pytest.raises(dataclasses.FrozenInstanceError):
		c.key = "other"


def test_proc_frozen_and_keyed():
	p = Proc(key="k", rc=0, stdout_path=Path("/tmp/out"), stderr_path=Path("/tmp/err"))
	assert p.key == "k"
	assert p.rc == 0
	with pytest.raises(dataclasses.FrozenInstanceError):
		p.rc = 1


def test_proc_rc_none_means_timeout():
	p = Proc(key="k", rc=None, stdout_path=Path("/tmp/out"), stderr_path=Path("/tmp/err"))
	assert p.rc is None


def test_randseed_frozen_and_keyed():
	rs = RandSeed(key="k", seed=12345, randseed_path=Path("/tmp/rs"), argv=["--seed", "12345"])
	assert rs.key == "k"
	assert rs.seed == 12345
	with pytest.raises(dataclasses.FrozenInstanceError):
		rs.key = "other"


def test_randseed_done_frozen_and_keyed():
	rsd = RandSeedDone(key="k")
	assert rsd.key == "k"
	with pytest.raises(dataclasses.FrozenInstanceError):
		rsd.key = "other"

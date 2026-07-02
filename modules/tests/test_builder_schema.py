"""Tests for modules/rtl_buddy/schema/builder.py — spec 01a acceptance criteria."""

import pytest
import typer

from modules.rtl_buddy.schema.builder import process_opts, RtlBuilderConfig, RtlBuilderConfigOpts


def make_builder_config(**overrides):
	defaults = {
		"name": "vcs",
		"exe": "vcs",
		"simv": "simv",
		"sim_rand_seed": 12345,
		"sim_rand_prefix": "+ntb_random_seed=",
		"opts": {
			"debug": RtlBuilderConfigOpts(compile_time=["-Wall", "-Wextra"], run_time=["-debug_access"]),
			"release": RtlBuilderConfigOpts(compile_time=["-O2"], run_time=["-fast"]),
		},
	}
	defaults.update(overrides)
	return RtlBuilderConfig(**defaults)


# ---------------------------------------------------------------------------
# process_opts happy paths
# ---------------------------------------------------------------------------


def test_process_opts_collapses_whitespace():
	assert process_opts("-Wall  -Wextra") == ["-Wall", "-Wextra"]


def test_process_opts_single_flag_with_surrounding_whitespace():
	assert process_opts("  -single-flag  ") == ["-single-flag"]


def test_process_opts_mixed_whitespace():
	assert process_opts("a\n\tb") == ["a", "b"]


# ---------------------------------------------------------------------------
# process_opts None passthrough (pyserde skips deserialiser for None)
# ---------------------------------------------------------------------------


def test_opts_none_compile_time():
	opts = RtlBuilderConfigOpts(compile_time=None, run_time=["-a"])
	assert opts.compile_time is None


def test_opts_none_run_time():
	opts = RtlBuilderConfigOpts(compile_time=["-a"], run_time=None)
	assert opts.run_time is None


# ---------------------------------------------------------------------------
# get_compile_time_opts / get_run_time_opts happy paths
# ---------------------------------------------------------------------------


def test_get_compile_time_opts_debug():
	cfg = make_builder_config()
	assert cfg.get_compile_time_opts("debug") == ["-Wall", "-Wextra"]


def test_get_run_time_opts_no_seed():
	cfg = make_builder_config()
	assert cfg.get_run_time_opts("debug") == ["-debug_access"]


def test_get_run_time_opts_with_seed():
	cfg = make_builder_config()
	assert cfg.get_run_time_opts("debug", seed=42) == ["-debug_access", "+ntb_random_seed=42"]


# ---------------------------------------------------------------------------
# log.fatal paths — missing mode and None opts
# ---------------------------------------------------------------------------


def test_get_compile_time_opts_missing_mode(logging_handler):
	cfg = make_builder_config()
	with pytest.raises(typer.Exit):
		cfg.get_compile_time_opts("nonexistent")


def test_get_compile_time_opts_none_compile_time(logging_handler):
	cfg = make_builder_config(opts={"debug": RtlBuilderConfigOpts(compile_time=None, run_time=["-a"])})
	with pytest.raises(typer.Exit):
		cfg.get_compile_time_opts("debug")


def test_get_run_time_opts_missing_mode(logging_handler):
	cfg = make_builder_config()
	with pytest.raises(typer.Exit):
		cfg.get_run_time_opts("nonexistent")


def test_get_run_time_opts_none_run_time(logging_handler):
	cfg = make_builder_config(opts={"debug": RtlBuilderConfigOpts(compile_time=["-a"], run_time=None)})
	with pytest.raises(typer.Exit):
		cfg.get_run_time_opts("debug")


# ---------------------------------------------------------------------------
# Result freshness — mutating the return must not corrupt the underlying
# ---------------------------------------------------------------------------


def test_compile_time_opts_freshness():
	cfg = make_builder_config()
	r1 = cfg.get_compile_time_opts("debug")
	r1.append("injected")
	r2 = cfg.get_compile_time_opts("debug")
	assert "injected" not in r2
	assert r2 == ["-Wall", "-Wextra"]


def test_run_time_opts_freshness():
	cfg = make_builder_config()
	r1 = cfg.get_run_time_opts("debug")
	r1.append("injected")
	r2 = cfg.get_run_time_opts("debug")
	assert "injected" not in r2
	assert r2 == ["-debug_access"]

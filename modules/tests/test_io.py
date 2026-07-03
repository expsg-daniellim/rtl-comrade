"""Tests for modules/io.py using the module testing harness."""

import importlib.util
import os
from pathlib import Path
from unittest.mock import patch

import pytest
import typer

from rtl_comrade.testing import run_module_scenario

_spec = importlib.util.spec_from_file_location("modules_io", Path(__file__).parent.parent / "io.py")
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
FileReadMod = _mod.FileReadMod
StdoutMod = _mod.StdoutMod


# ---------------------------------------------------------------------------
# FileReadMod
# ---------------------------------------------------------------------------


async def test_fileread_yields_lines(tmp_path):
	f = tmp_path / "data.txt"
	f.write_text("hello\nworld\n")
	await run_module_scenario(
		FileReadMod,
		input_sequence=[{}],
		expected_emissions={"default": ["hello\n", "world\n"]},
		config=FileReadMod.Config(file=f),
	)


async def test_fileread_single_line_no_trailing_newline(tmp_path):
	f = tmp_path / "data.txt"
	f.write_text("only line")
	await run_module_scenario(
		FileReadMod,
		input_sequence=[{}],
		expected_emissions={"default": ["only line"]},
		config=FileReadMod.Config(file=f),
	)


async def test_fileread_empty_file(tmp_path):
	f = tmp_path / "empty.txt"
	f.write_text("")
	await run_module_scenario(
		FileReadMod,
		input_sequence=[{}],
		expected_emissions={},
		config=FileReadMod.Config(file=f),
	)


async def test_fileread_not_found(logging_handler):
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			FileReadMod,
			input_sequence=[{}],
			expected_emissions={},
			config=FileReadMod.Config(file=Path("/nonexistent/path/file.txt")),
		)


async def test_fileread_is_directory(logging_handler, tmp_path):
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			FileReadMod,
			input_sequence=[{}],
			expected_emissions={},
			config=FileReadMod.Config(file=tmp_path),
		)


async def test_fileread_unicode_error(logging_handler, tmp_path):
	f = tmp_path / "bad.txt"
	f.write_bytes(b"\x80\x81invalid utf-8")
	with pytest.raises(typer.Exit):
		await run_module_scenario(
			FileReadMod,
			input_sequence=[{}],
			expected_emissions={},
			config=FileReadMod.Config(file=f),
		)


async def test_fileread_os_error(logging_handler, tmp_path):
	f = tmp_path / "data.txt"
	f.write_text("hello")
	with patch("builtins.open", side_effect=OSError(5, "Input/output error")):
		with pytest.raises(typer.Exit):
			await run_module_scenario(
				FileReadMod,
				input_sequence=[{}],
				expected_emissions={},
				config=FileReadMod.Config(file=f),
			)


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses file-mode enforcement, so chmod 0o000 grants no denial")
async def test_fileread_permission_denied(logging_handler, tmp_path):
	f = tmp_path / "secret.txt"
	f.write_text("secret data")
	f.chmod(0o000)
	try:
		with pytest.raises(typer.Exit):
			await run_module_scenario(
				FileReadMod,
				input_sequence=[{}],
				expected_emissions={},
				config=FileReadMod.Config(file=f),
			)
	finally:
		f.chmod(0o644)


# ---------------------------------------------------------------------------
# StdoutMod
# ---------------------------------------------------------------------------


async def test_stdout_no_emission(capsys):
	await run_module_scenario(
		StdoutMod,
		input_sequence=[{"a": "hello"}],
		expected_emissions={},
	)
	assert capsys.readouterr().out == "hello\n"


async def test_stdout_prints_non_string(capsys):
	await run_module_scenario(
		StdoutMod,
		input_sequence=[{"a": 42}],
		expected_emissions={},
	)
	assert capsys.readouterr().out == "42\n"


async def test_stdout_multi_step(capsys):
	await run_module_scenario(
		StdoutMod,
		input_sequence=[{"a": "foo"}, {"a": "bar"}],
		expected_emissions={},
	)
	assert capsys.readouterr().out == "foo\nbar\n"

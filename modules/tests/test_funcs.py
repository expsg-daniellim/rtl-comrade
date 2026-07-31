"""Tests for modules/funcs.py using the module testing harness."""

import importlib.util
from pathlib import Path


from rtl_comrade.testing import run_module_scenario

_spec = importlib.util.spec_from_file_location("modules_funcs", Path(__file__).parent.parent / "funcs.py")
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
AddMod = _mod.AddMod
ALUMod = _mod.ALUMod
DirnameMod = _mod.DirnameMod


# ---------------------------------------------------------------------------
# AddMod
# ---------------------------------------------------------------------------


async def test_add_integers():
	await run_module_scenario(
		AddMod,
		input_sequence=[{"a": 3, "b": 4}],
		expected_emissions={"default": [7]},
	)


async def test_add_coerces_strings():
	await run_module_scenario(
		AddMod,
		input_sequence=[{"a": "3", "b": "4"}],
		expected_emissions={"default": [7]},
	)


async def test_add_negative():
	await run_module_scenario(
		AddMod,
		input_sequence=[{"a": -5, "b": 3}],
		expected_emissions={"default": [-2]},
	)


async def test_add_multi_step():
	await run_module_scenario(
		AddMod,
		input_sequence=[{"a": 1, "b": 2}, {"a": 10, "b": 20}],
		expected_emissions={"default": [3, 30]},
	)


# ---------------------------------------------------------------------------
# ALUMod
# ---------------------------------------------------------------------------


async def test_alu_op0_add():
	await run_module_scenario(
		ALUMod,
		input_sequence=[{"a": 10, "b": 3, "op": 0}],
		expected_emissions={"default": [13]},
	)


async def test_alu_op1_subtract():
	await run_module_scenario(
		ALUMod,
		input_sequence=[{"a": 10, "b": 3, "op": 1}],
		expected_emissions={"default": [7]},
	)


async def test_alu_invalid_op_no_emission(logging_handler):
	await run_module_scenario(
		ALUMod,
		input_sequence=[{"a": 10, "b": 3, "op": 2}],
		expected_emissions={},
	)
	assert logging_handler.failure is True


async def test_alu_coerces_strings():
	await run_module_scenario(
		ALUMod,
		input_sequence=[{"a": "5", "b": "3", "op": "0"}],
		expected_emissions={"default": [8]},
	)


async def test_alu_multi_step():
	await run_module_scenario(
		ALUMod,
		input_sequence=[
			{"a": 10, "b": 3, "op": 0},
			{"a": 10, "b": 3, "op": 1},
		],
		expected_emissions={"default": [13, 7]},
	)


# ---------------------------------------------------------------------------
# DirnameMod
# ---------------------------------------------------------------------------


async def test_dirname_file(tmp_path):
	build = tmp_path / "build"
	build.mkdir()
	runf = build / "run.f"
	runf.touch()
	await run_module_scenario(
		DirnameMod,
		input_sequence=[{"path": str(runf)}],
		expected_emissions={"default": [build]},
	)


async def test_dirname_directory(tmp_path):
	build = tmp_path / "build"
	build.mkdir()
	await run_module_scenario(
		DirnameMod,
		input_sequence=[{"path": str(build)}],
		expected_emissions={"default": [build]},
	)


async def test_dirname_nonexistent():
	await run_module_scenario(
		DirnameMod,
		input_sequence=[{"path": "/nonexistent/run.f"}],
		expected_emissions={"default": [Path("/nonexistent")]},
	)


async def test_dirname_bare_filename_fallback():
	await run_module_scenario(
		DirnameMod,
		input_sequence=[{"path": "run.f"}],
		expected_emissions={"default": [Path(".")]},
	)


async def test_dirname_abs_nonexistent():
	await run_module_scenario(
		DirnameMod,
		input_sequence=[{"path": "/abs/dir/run.f"}],
		expected_emissions={"default": [Path("/abs/dir")]},
	)


async def test_dirname_path_input(tmp_path):
	build = tmp_path / "build"
	build.mkdir()
	runf = build / "run.f"
	runf.touch()
	await run_module_scenario(
		DirnameMod,
		input_sequence=[{"path": runf}],
		expected_emissions={"default": [build]},
	)

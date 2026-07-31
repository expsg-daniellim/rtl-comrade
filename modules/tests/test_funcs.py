"""Tests for modules/funcs.py using the module testing harness."""

import importlib.util
from collections import OrderedDict
from pathlib import Path
from types import SimpleNamespace

import pytest
import typer

from rtl_comrade.testing import run_module_scenario

_spec = importlib.util.spec_from_file_location("modules_funcs", Path(__file__).parent.parent / "funcs.py")
assert _spec is not None
assert _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
AddMod = _mod.AddMod
ALUMod = _mod.ALUMod
DirnameMod = _mod.DirnameMod
DirjoinMod = _mod.DirjoinMod
LoggerMod = _mod.LoggerMod
LOG_LEVELS = _mod.LOG_LEVELS
ConstantMod = _mod.ConstantMod


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


# ---------------------------------------------------------------------------
# DirjoinMod
# ---------------------------------------------------------------------------


async def test_dirjoin_bare_filename():
	await run_module_scenario(
		DirjoinMod,
		input_sequence=[{"dir_": Path("/work"), "name": "models.yaml"}],
		expected_emissions={"default": [Path("/work/models.yaml")]},
	)


async def test_dirjoin_relative_with_components():
	await run_module_scenario(
		DirjoinMod,
		input_sequence=[{"dir_": Path("/work"), "name": "sub/models.yaml"}],
		expected_emissions={"default": [Path("/work/sub/models.yaml")]},
	)


async def test_dirjoin_absolute_name_replaces_dir():
	await run_module_scenario(
		DirjoinMod,
		input_sequence=[{"dir_": Path("/work"), "name": Path("/abs/models.yaml")}],
		expected_emissions={"default": [Path("/abs/models.yaml")]},
	)


async def test_dirjoin_path_name_input():
	await run_module_scenario(
		DirjoinMod,
		input_sequence=[{"dir_": Path("/work"), "name": Path("models.yaml")}],
		expected_emissions={"default": [Path("/work/models.yaml")]},
	)


# ---------------------------------------------------------------------------
# LoggerMod
# ---------------------------------------------------------------------------


def spy_emit(mod):
	"""Wrap mod.emit to record calls while delegating to the original."""
	calls = []
	original = mod.emit
	def wrapper(event, **kwargs):
		calls.append({"event": event, **kwargs})
		return original(event, **kwargs)
	mod.emit = wrapper
	return calls


def test_logger_dict_mapping_nested_payload(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"path": "filelist.path"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value=SimpleNamespace(filelist=SimpleNamespace(path="/foo/bar")))
	assert result is None
	assert calls == [{"event": "test_event", "path": "/foo/bar"}]
	assert logging_handler.failure is False


def test_logger_dict_mapping_dict_payload(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"path": "filelist.path"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value={"filelist": {"path": "/foo/bar"}})
	assert result is None
	assert calls == [{"event": "test_event", "path": "/foo/bar"}]
	assert logging_handler.failure is False


def test_logger_str_mapping(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping="path")
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value="/foo/bar")
	assert result is None
	assert calls == [{"event": "test_event", "path": "/foo/bar"}]
	assert logging_handler.failure is False


def test_logger_unresolved_no_constant(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"path": "missing", "key": "key"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value=SimpleNamespace(key="k1"))
	assert result is None
	assert logging_handler.failure is True
	assert len(calls) == 1
	assert "path" not in calls[0]
	assert calls[0]["key"] == "k1"
	assert calls[0]["event"] == "test_event"


def test_logger_unresolved_non_subscriptable(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"val": "x.y"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value=SimpleNamespace(x=42))
	assert result is None
	assert logging_handler.failure is True
	assert len(calls) == 1
	assert "val" not in calls[0]


def test_logger_constants_fixed_field(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"path": "path"}, constants={"context": "filelist.write"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value=SimpleNamespace(path="/foo"))
	assert result is None
	assert calls == [{"event": "test_event", "path": "/foo", "context": "filelist.write"}]
	assert logging_handler.failure is False


def test_logger_unresolved_with_constant(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"path": "missing"}, constants={"path": "/default"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value=SimpleNamespace())
	assert result is None
	assert calls == [{"event": "test_event", "path": "/default"}]
	assert logging_handler.failure is False


def test_logger_resolved_overrides_constant(logging_handler):
	cfg = LoggerMod.Config(event="test_event", mapping={"path": "path"}, constants={"path": "/default"})
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value=SimpleNamespace(path="/actual"))
	assert result is None
	assert calls == [{"event": "test_event", "path": "/actual"}]
	assert logging_handler.failure is False


def test_logger_level_error(logging_handler):
	cfg = LoggerMod.Config(level="error", event="test_event", mapping="value")
	mod = LoggerMod(config=cfg)
	calls = spy_emit(mod)
	result = mod.run(value="hello")
	assert result is None
	assert calls == [{"event": "test_event", "value": "hello"}]
	assert logging_handler.failure is True


def test_logger_invalid_level(logging_handler):
	with pytest.raises(typer.Exit):
		LoggerMod(config=LoggerMod.Config(level="nonsense"))


def test_logger_reserved_mapping_event(logging_handler):
	with pytest.raises(typer.Exit):
		LoggerMod(config=LoggerMod.Config(mapping={"event": "x"}))


def test_logger_reserved_constants_event(logging_handler):
	with pytest.raises(typer.Exit):
		LoggerMod(config=LoggerMod.Config(constants={"event": "x"}))


def test_logger_reserved_mapping_exc_info(logging_handler):
	with pytest.raises(typer.Exit):
		LoggerMod(config=LoggerMod.Config(mapping={"exc_info": "x"}))


def test_logger_reserved_constants_stack_info(logging_handler):
	with pytest.raises(typer.Exit):
		LoggerMod(config=LoggerMod.Config(constants={"stack_info": "x"}))


async def test_logger_no_emissions(logging_handler):
	await run_module_scenario(
		LoggerMod,
		input_sequence=[{"value": "hello"}],
		expected_emissions={},
		config=LoggerMod.Config(event="test_event", mapping="value"),
	)


# ---------------------------------------------------------------------------
# ConstantMod — bare value
# ---------------------------------------------------------------------------


async def test_constant_bare_true():
	await run_module_scenario(ConstantMod, input_sequence=[{}], expected_emissions={"default": [True]}, config=ConstantMod.Config(value=True))


def test_constant_bare_payload_agnostic():
	for val in ["hello", 42, [1, 2, 3]]:
		mod = ConstantMod(config=ConstantMod.Config(value=val))
		assert mod.run() == ("default", val)


def test_constant_bare_identity():
	sentinel = [1, 2, 3]
	mod = ConstantMod(config=ConstantMod.Config(value=sentinel))
	assert mod.run()[1] is sentinel


def test_constant_bare_repeat():
	mod = ConstantMod(config=ConstantMod.Config(value=42))
	assert mod.run() == ("default", 42)
	assert mod.run() == ("default", 42)


def test_constant_missing_value(logging_handler):
	with pytest.raises(typer.Exit):
		ConstantMod(config=ConstantMod.Config())


# ---------------------------------------------------------------------------
# ConstantMod — constructed value
# ---------------------------------------------------------------------------


def test_constant_type_path():
	mod = ConstantMod(config=ConstantMod.Config(type="pathlib:Path", value="/tmp"))
	result = mod.run()
	assert result == ("default", Path("/tmp"))
	assert isinstance(result[1], Path)


def test_constant_type_path_args():
	mod = ConstantMod(config=ConstantMod.Config(type="pathlib:Path", args=["/tmp", "sub"]))
	assert mod.run() == ("default", Path("/tmp", "sub"))


def test_constant_type_ordered_dict_kwargs():
	mod = ConstantMod(config=ConstantMod.Config(type="collections:OrderedDict", kwargs={"a": 1, "b": 2}))
	result = mod.run()
	assert isinstance(result[1], OrderedDict)
	assert result[1] == OrderedDict(a=1, b=2)


def test_constant_type_args_over_value():
	mod = ConstantMod(config=ConstantMod.Config(type="pathlib:Path", args=["/tmp"], value="ignored"))
	assert mod.run() == ("default", Path("/tmp"))


def test_constant_unimportable_type():
	with pytest.raises(ModuleNotFoundError):
		ConstantMod(config=ConstantMod.Config(type="nonexistent.module:Foo"))


def test_constant_absent_class():
	with pytest.raises(AttributeError):
		ConstantMod(config=ConstantMod.Config(type="pathlib:NonexistentClass"))

"""Tests for the module testing harness (run_module_scenario)."""

import asyncio

import pytest

from rtl_comrade.testing import run_module_scenario


class _SyncDefaultModule:
	def run(self, x):
		return x * 2


class _SyncNoneModule:
	def run(self, x):
		return None


class _SyncNamedPortModule:
	def run(self, x):
		return ("out", x + 1)


class _SyncGeneratorModule:
	def run(self, x):
		yield x
		yield x + 1
		yield x + 2


class _AsyncDefaultModule:
	async def run(self, x):
		return x * 3


class _AsyncGeneratorModule:
	async def run(self, x):
		yield x
		yield x * 10


class _SourceModule:
	def run(self):
		return 99


class _MultiStepModule:
	def run(self, a):
		return a


class _MalformedTupleModule:
	def run(self):
		return (1, 2, 3)


class _NonStrPortModule:
	def run(self):
		return (42, "value")


class _ModuleWithConfig:
	def __init__(self, config):
		self.multiplier = config

	def run(self, x):
		return x * self.multiplier


class _ModuleWithId:
	def __init__(self, id):
		self.my_id = id

	def run(self):
		return self.my_id


async def test_sync_module_default_port():
	await run_module_scenario(
		_SyncDefaultModule,
		input_sequence=[{"x": 5}],
		expected_emissions={"default": [10]},
	)


async def test_sync_module_none_return_no_emission():
	await run_module_scenario(
		_SyncNoneModule,
		input_sequence=[{"x": 5}],
		expected_emissions={},
	)


async def test_sync_module_named_port():
	await run_module_scenario(
		_SyncNamedPortModule,
		input_sequence=[{"x": 4}],
		expected_emissions={"out": [5]},
	)


async def test_sync_generator_multiple_emissions():
	await run_module_scenario(
		_SyncGeneratorModule,
		input_sequence=[{"x": 10}],
		expected_emissions={"default": [10, 11, 12]},
	)


async def test_async_module_default_port():
	await run_module_scenario(
		_AsyncDefaultModule,
		input_sequence=[{"x": 7}],
		expected_emissions={"default": [21]},
	)


async def test_async_generator_multiple_emissions():
	await run_module_scenario(
		_AsyncGeneratorModule,
		input_sequence=[{"x": 3}],
		expected_emissions={"default": [3, 30]},
	)


async def test_multi_step_sequence_collects_across_steps():
	await run_module_scenario(
		_MultiStepModule,
		input_sequence=[{"a": 1}, {"a": 2}, {"a": 3}],
		expected_emissions={"default": [1, 2, 3]},
	)


async def test_source_module_runs_once():
	await run_module_scenario(
		_SourceModule,
		input_sequence=[{}],
		expected_emissions={"default": [99]},
	)


async def test_source_module_extra_dicts_ignored():
	await run_module_scenario(
		_SourceModule,
		input_sequence=[{}, {}],
		expected_emissions={"default": [99]},
	)


async def test_malformed_tuple_raises_assertion():
	with pytest.raises(AssertionError, match="malformed tuple"):
		await run_module_scenario(
			_MalformedTupleModule,
			input_sequence=[{}],
			expected_emissions={},
		)


async def test_non_string_port_name_raises_assertion():
	with pytest.raises(AssertionError, match="non-string port name"):
		await run_module_scenario(
			_NonStrPortModule,
			input_sequence=[{}],
			expected_emissions={},
		)


async def test_expected_vs_actual_mismatch_raises_assertion():
	with pytest.raises(AssertionError, match=r"emission\[0\]"):
		await run_module_scenario(
			_SyncDefaultModule,
			input_sequence=[{"x": 5}],
			expected_emissions={"default": [999]},
		)


async def test_unexpected_emission_raises_assertion():
	with pytest.raises(AssertionError, match="unexpected emissions"):
		await run_module_scenario(
			_SyncDefaultModule,
			input_sequence=[{"x": 5}],
			expected_emissions={},
		)


async def test_expected_port_not_emitted_raises_assertion():
	with pytest.raises(AssertionError, match="expected 1 emission"):
		await run_module_scenario(
			_SyncNoneModule,
			input_sequence=[{"x": 5}],
			expected_emissions={"default": [42]},
		)


async def test_config_passed_to_module():
	await run_module_scenario(
		_ModuleWithConfig,
		input_sequence=[{"x": 6}],
		expected_emissions={"default": [18]},
		config=3,
	)


async def test_id_passed_to_module():
	await run_module_scenario(
		_ModuleWithId,
		input_sequence=[{}],
		expected_emissions={"default": ["test.module"]},
		module_id="test.module",
	)


def test_validation_rejects_missing_run():
	class NoRun:
		pass

	with pytest.raises(AssertionError, match="must expose run"):
		asyncio.run(run_module_scenario(NoRun, input_sequence=[], expected_emissions={}))

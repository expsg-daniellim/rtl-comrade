"""Tests for UnitContract."""

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario

from contracts.unit import UnitContract


async def test_single_port_invokes_once():
	await run_contract_scenario(
		UnitContract,
		port_inputs={"a": [42, EndSentinel("src")]},
		expected_outputs=[{"a": 42}, EndSentinel("test")],
	)


async def test_multiple_ports_invokes_once():
	await run_contract_scenario(
		UnitContract,
		port_inputs={"a": [1, EndSentinel("src")], "b": [2, EndSentinel("src")]},
		expected_outputs=[{"a": 1, "b": 2}, EndSentinel("test")],
	)


async def test_missing_required_input_logs_error(logging_handler):
	await run_contract_scenario(
		UnitContract,
		port_inputs={"a": [EndSentinel("src")]},
		expected_outputs=[EndSentinel("test")],
	)
	assert logging_handler.failure is True


async def test_missing_one_of_multiple_ports_logs_error(logging_handler):
	# "b" ends before sending any data
	await run_contract_scenario(
		UnitContract,
		port_inputs={"a": [1], "b": [EndSentinel("src")]},
		expected_outputs=[EndSentinel("test")],
	)
	assert logging_handler.failure is True


async def test_duplicate_input_logs_error(logging_handler):
	# "a" sends two items; the second is detected as a duplicate on the second call
	await run_contract_scenario(
		UnitContract,
		port_inputs={"a": [1, 2]},
		expected_outputs=[{"a": 1}, EndSentinel("test")],
	)
	assert logging_handler.failure is True

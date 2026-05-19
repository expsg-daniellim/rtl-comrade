"""Tests for ZipContract."""

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario

from contracts.zip import ZipContract


async def test_two_ports_full_sequence():
	await run_contract_scenario(
		ZipContract,
		port_inputs={
			"a": [1, 2, EndSentinel("src")],
			"b": [10, 20, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": 1, "b": 10},
			{"a": 2, "b": 20},
			EndSentinel("test"),
		],
	)


async def test_single_port():
	await run_contract_scenario(
		ZipContract,
		port_inputs={"x": [42, EndSentinel("src")]},
		expected_outputs=[{"x": 42}, EndSentinel("test")],
	)


async def test_three_ports():
	await run_contract_scenario(
		ZipContract,
		port_inputs={
			"a": [1, EndSentinel("src")],
			"b": [2, EndSentinel("src")],
			"c": [3, EndSentinel("src")],
		},
		expected_outputs=[{"a": 1, "b": 2, "c": 3}, EndSentinel("test")],
	)


async def test_mismatched_ends_logs_error_and_returns_sentinel(logging_handler):
	await run_contract_scenario(
		ZipContract,
		port_inputs={
			"a": [EndSentinel("src")],
			"b": [99],
		},
		expected_outputs=[EndSentinel("test")],
	)
	assert logging_handler.failure is True

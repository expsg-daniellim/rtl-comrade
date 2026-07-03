"""Tests for ZipContract."""

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortMeta

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


async def test_branch_divergence_across_partitions_no_error(logging_handler):
	# "a" belongs to a branch arm that ended while co-independent "b" stays live; a data/end split across partitions is a legitimate branch outcome, not a desync.
	await run_contract_scenario(
		ZipContract,
		port_inputs={
			"a": [EndSentinel("src")],
			"b": [99],
		},
		expected_outputs=[EndSentinel("test")],
		port_meta={"a": PortMeta(branch_labels=frozenset({("origin", frozenset({"a"}))}))},
	)
	assert logging_handler.failure is False

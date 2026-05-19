"""Tests for LatestContract."""

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortTestInput

from contracts.latest import LatestContract

_CFG = LatestContract.Config(trigger_ports=["trigger"])


async def test_trigger_uses_latest_state():
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [10, EndSentinel("src")],
			"trigger": [1, EndSentinel("src")],
		},
		expected_outputs=[
			{"state": 10, "trigger": 1},
			EndSentinel("test"),
		],
		config=_CFG,
	)


async def test_multiple_triggers_reuse_state():
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [10, EndSentinel("src")],
			"trigger": [1, 2, EndSentinel("src")],
		},
		expected_outputs=[
			{"state": 10, "trigger": 1},
			{"state": 10, "trigger": 2},
			EndSentinel("test"),
		],
		config=_CFG,
	)


async def test_state_updates_before_trigger():
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [10, 20, EndSentinel("src")],
			"trigger": [1, 2, EndSentinel("src")],
		},
		expected_outputs=[
			{"state": 20, "trigger": 1},
			{"state": 20, "trigger": 2},
			EndSentinel("test"),
		],
		config=_CFG,
	)


async def test_trigger_port_end_returns_sentinel():
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [10, EndSentinel("src")],
			"trigger": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test")],
		config=_CFG,
	)


async def test_state_port_ends_before_data_returns_sentinel():
	# State delivers only EndSentinel — hits the return on line 36 inside the
	# initial await loop before _latest is populated.
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [EndSentinel("src")],
			"trigger": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test")],
		config=_CFG,
	)


async def test_empty_state_queue_during_drain():
	# State arrives asynchronously so its queue is empty when the drain loop
	# runs after the initial await — hits try_get() → None → break (line 43).
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [
				PortTestInput(10, delay=1),
				PortTestInput(EndSentinel("src"), delay=3),
			],
			"trigger": [
				PortTestInput(1, delay=2),
				PortTestInput(EndSentinel("src"), delay=4),
			],
		},
		expected_outputs=[{"state": 10, "trigger": 1}, EndSentinel("test")],
		config=_CFG,
	)


async def test_all_trigger_ports_already_ended():
	# Trigger ends on the first call; the second call finds trigger.has_ended()
	# True, skips the for-loop body entirely, and falls through to line 57.
	await run_contract_scenario(
		LatestContract,
		port_inputs={
			"state": [10, EndSentinel("src")],
			"trigger": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test"), EndSentinel("test")],
		config=_CFG,
	)

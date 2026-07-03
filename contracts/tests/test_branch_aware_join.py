"""Tests for BranchAwareJoinContract."""

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortTestInput, PortMeta

from contracts.branch_aware_join import BranchAwareJoinContract

_CFG = BranchAwareJoinContract.Config(key_field="id")

# Ports "a" and "b" are the two arms of one origin "router": each key takes exactly one.
A_ARM = PortMeta(branch_labels=frozenset({("router", frozenset({"a"}))}))
B_ARM = PortMeta(branch_labels=frozenset({("router", frozenset({"b"}))}))


async def test_unbranched_ports_and_join():
	# Ports with no branch labels are unconditional participants: a key is emitted only once both hold it.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1, "v": "A"}, EndSentinel("src")],
			"b": [{"id": 1, "v": "B"}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1, "v": "A"}, "b": {"id": 1, "v": "B"}},
			EndSentinel("test"),
		],
		config=_CFG,
	)


async def test_coarm_exclusion_routes_each_key():
	# Each key lands on exactly one arm; the co-arm sibling is excluded for that key from its labels alone.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"b": [{"id": 2}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}},
			{"b": {"id": 2}},
			EndSentinel("test"),
		],
		port_meta={"a": A_ARM, "b": B_ARM},
		config=_CFG,
	)


async def test_early_exclusion_without_sibling_end():
	# Key 1 arrives on arm a; arm b is still live (no key 1, not ended), yet the join emits {a} at once
	# because b is a co-arm sibling — excluded by structure, no end or skip signal needed.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1}],
			"b": [PortTestInput({"id": 2}, delay=5)],
		},
		expected_outputs=[{"a": {"id": 1}}],
		port_meta={"a": A_ARM, "b": B_ARM},
		config=_CFG,
	)


async def test_skip_via_port_end():
	# An unbranched port that never delivers key 1 but ends is excluded from it by ending; key 1 emits {a}.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"b": [EndSentinel("src")],
		},
		expected_outputs=[{"a": {"id": 1}}, EndSentinel("test")],
		config=_CFG,
	)


async def test_unbranched_participant_awaited():
	# a routes key 1; unbranched c is required and arrives late — the join waits for it before emitting.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1}, PortTestInput(EndSentinel("src"), delay=3)],
			"c": [PortTestInput({"id": 1}, delay=1), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[{"a": {"id": 1}, "c": {"id": 1}}, EndSentinel("test")],
		port_meta={"a": A_ARM},
		config=_CFG,
	)


async def test_does_not_terminate_on_first_end():
	# Arm a delivers key 1 and ends while co-arm b is still live; the join must keep going for b's key 2.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"b": [PortTestInput({"id": 2}, delay=2), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[
			{"a": {"id": 1}},
			{"b": {"id": 2}},
			EndSentinel("test"),
		],
		port_meta={"a": A_ARM, "b": B_ARM},
		config=_CFG,
	)


async def test_conflicting_arms_logs_error(logging_handler):
	# Both arms of the same origin hold key 1 — an origin cannot select two arms for one key.
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"b": [{"id": 1}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}, "b": {"id": 1}},
			EndSentinel("test"),
		],
		port_meta={"a": A_ARM, "b": B_ARM},
		config=_CFG,
	)
	assert logging_handler.failure is True


async def test_blocking_await_receives_data():
	# A single port with a deferred item: try_get returns None, the contract blocks on await port.get().
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={"a": [PortTestInput({"id": 1}, delay=1)]},
		expected_outputs=[{"a": {"id": 1}}],
		config=_CFG,
	)


async def test_all_ports_end_returns_sentinel():
	await run_contract_scenario(
		BranchAwareJoinContract,
		port_inputs={
			"a": [EndSentinel("src")],
			"b": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test")],
		config=_CFG,
	)

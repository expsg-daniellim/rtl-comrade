"""Tests for KeyedJoinContract."""

from dataclasses import dataclass
from typing import Any

import pytest
import typer

from rtl_comrade.api import ContractPort, EndSentinel, Payload
from rtl_comrade.port import Port
from rtl_comrade.testing import run_contract_scenario, PortTestInput, PortMeta

from contracts.keyed_join import KeyedJoinContract
from contracts.sentinels import KeyedValue

CFG = KeyedJoinContract.Config(key_field="id")


@dataclass(frozen=True)
class Keyed:
	"""A non-dict payload that exposes its correlation key as an attribute."""
	key: Any
	v: str = ""


async def test_single_key_two_ports():
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1, "v": "A"}, EndSentinel("src")],
			"b": [{"id": 1, "v": "B"}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1, "v": "A"}, "b": {"id": 1, "v": "B"}},
			EndSentinel("test"),
		],
		config=CFG,
	)


async def test_multiple_keys_in_order():
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, {"id": 2}, EndSentinel("src")],
			"b": [{"id": 1}, {"id": 2}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}, "b": {"id": 1}},
			{"a": {"id": 2}, "b": {"id": 2}},
			EndSentinel("test"),
		],
		config=CFG,
	)


async def test_interleaved_keys():
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, {"id": 2}, EndSentinel("src")],
			"b": [{"id": 2}, {"id": 1}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}, "b": {"id": 1}},
			{"a": {"id": 2}, "b": {"id": 2}},
			EndSentinel("test"),
		],
		config=CFG,
	)


async def test_blocking_await_receives_data():
	# delay=1 starts the queue empty so try_get() returns None (line 38) and
	# the contract blocks on await port.get() (lines 58-66) before the item arrives.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={"a": [PortTestInput({"id": 1}, delay=1)]},
		expected_outputs=[{"a": {"id": 1}}],
		config=CFG,
	)


async def test_blocking_await_receives_end_sentinel():
	# EndSentinel arriving via blocking await covers lines 61-62.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={"a": [PortTestInput(EndSentinel("src"), delay=1)]},
		expected_outputs=[EndSentinel("test")],
		config=CFG,
	)


async def test_incomplete_key_at_stream_end_logs_error(logging_handler):
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1, "v": "A"}, EndSentinel("src")],
			"b": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test")],
		config=CFG,
	)
	assert logging_handler.failure is True


async def test_unselected_branch_arm_incomplete_key_not_error(logging_handler):
	# Keyed port "b" belongs to a branch arm that was not selected: it ends without key 1 while "a" (a separate partition) buffered it. The key is not co-fated-incomplete, so no error is logged.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1, "v": "A"}, EndSentinel("src")],
			"b": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test")],
		port_meta={"b": PortMeta(branch_labels=frozenset({("origin", frozenset({"b"}))}))},
		config=CFG,
	)
	assert logging_handler.failure is False


async def test_lagging_keyed_port_awaited_not_terminated(logging_handler):
	# Two keyed ports deliver key 1 and end before the third (proc-like) port produces it. The
	# join must wait for the lagging port rather than terminating on the early ends (Bug A).
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"b": [{"id": 1}, EndSentinel("src")],
			"c": [PortTestInput({"id": 1}, delay=2), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "b": {"id": 1}, "c": {"id": 1}},
			EndSentinel("test"),
		],
		config=CFG,
	)
	assert logging_handler.failure is False


async def test_key_completed_after_one_port_ends():
	# Port a ends having buffered key 2; port b delivers key 2 only afterwards. The key still
	# completes because the join waits for all keyed ports to end, not just the first.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, {"id": 2}, EndSentinel("src")],
			"b": [PortTestInput({"id": 1}, delay=1), PortTestInput({"id": 2}, delay=3), PortTestInput(EndSentinel("src"), delay=4)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "b": {"id": 1}},
			{"a": {"id": 2}, "b": {"id": 2}},
			EndSentinel("test"),
		],
		config=CFG,
	)


async def test_object_payloads_keyed_by_attribute():
	# Payloads are objects exposing the key_field as an attribute rather than dicts; the
	# contract correlates them by that attribute. key_field defaults to "key" here.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [Keyed(key=1, v="A"), Keyed(key=2, v="A2"), EndSentinel("src")],
			"b": [Keyed(key=2, v="B2"), Keyed(key=1, v="B"), EndSentinel("src")],
		},
		expected_outputs=[
			{"a": Keyed(key=1, v="A"), "b": Keyed(key=1, v="B")},
			{"a": Keyed(key=2, v="A2"), "b": Keyed(key=2, v="B2")},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(),
	)


PERSIST_CFG = KeyedJoinContract.Config(key_field="id", persistent_inputs=["cfg"])


async def test_persistent_object_payload_cached_by_attribute():
	# A persistent input delivering an object with a `key` attribute is cached per key;
	# the keyed assembly for that key prefers it, other keys fall back to the latest value.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [Keyed(key=1), Keyed(key=2), EndSentinel("src")],
			"cfg": [Keyed(key=1, v="for-1"), Keyed(key="x", v="latest"), EndSentinel("src")],
		},
		expected_outputs=[
			{"a": Keyed(key=1), "cfg": Keyed(key=1, v="for-1")},
			{"a": Keyed(key=2), "cfg": Keyed(key="x", v="latest")},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(persistent_inputs=["cfg"]),
	)


async def test_persistent_singleton_replayed_across_keys():
	# A keyless persistent value is replayed verbatim on every keyed assembly.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, {"id": 2}, EndSentinel("src")],
			"cfg": [{"opt": "X"}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg": {"opt": "X"}},
			{"a": {"id": 2}, "cfg": {"opt": "X"}},
			EndSentinel("test"),
		],
		config=PERSIST_CFG,
	)


async def test_persistent_value_updates_midstream():
	# A new persistent value replaces the cached one for subsequent keyed assemblies.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [PortTestInput({"id": 1}, delay=1), PortTestInput({"id": 2}, delay=3), PortTestInput(EndSentinel("src"), delay=4)],
			"cfg": [PortTestInput({"opt": "X"}, delay=1), PortTestInput({"opt": "Y"}, delay=2), PortTestInput(EndSentinel("src"), delay=5)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg": {"opt": "X"}},
			{"a": {"id": 2}, "cfg": {"opt": "Y"}},
			EndSentinel("test"),
		],
		config=PERSIST_CFG,
	)


async def test_persistent_keyed_value_preferred_with_fallback():
	# When a persistent payload carries key_field, the per-key value wins for its key;
	# a key with no per-key value falls back to the most-recent value.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, {"id": 2}, EndSentinel("src")],
			"cfg": [{"id": 1, "opt": "for-1"}, {"opt": "latest"}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg": {"id": 1, "opt": "for-1"}},
			{"a": {"id": 2}, "cfg": {"opt": "latest"}},
			EndSentinel("test"),
		],
		config=PERSIST_CFG,
	)


async def test_persistent_first_run_blocks_until_value_arrives():
	# A complete keyed group is withheld until the persistent value arrives (delay=2).
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"cfg": [PortTestInput({"opt": "X"}, delay=2), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg": {"opt": "X"}},
			EndSentinel("test"),
		],
		config=PERSIST_CFG,
	)


async def test_persistent_end_does_not_terminate_join():
	# The persistent port ends after delivering; the join keeps emitting keyed groups,
	# replaying the last persistent value, until the keyed port ends.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"cfg": [{"opt": "X"}, EndSentinel("src")],
			"a": [{"id": 1}, {"id": 2}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg": {"opt": "X"}},
			{"a": {"id": 2}, "cfg": {"opt": "X"}},
			EndSentinel("test"),
		],
		config=PERSIST_CFG,
	)


async def test_persistent_ended_without_value_omits_input(logging_handler):
	# A persistent port that ends before delivering any value is logged as an error,
	# and the keyed assembly proceeds without it (module default applies).
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"cfg": [PortTestInput(EndSentinel("src"), delay=2)],
		},
		expected_outputs=[
			{"a": {"id": 1}},
			EndSentinel("test"),
		],
		config=PERSIST_CFG,
	)
	assert logging_handler.failure is True


async def test_multiple_persistent_inputs_block_independently():
	# With two persistent inputs, one already cached, the first-run gate blocks only on
	# the one still missing its value before the complete keyed group is emitted.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"cfg1": [{"opt": "X"}],
			"cfg2": [PortTestInput({"opt": "Y"}, delay=2)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg1": {"opt": "X"}, "cfg2": {"opt": "Y"}},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(key_field="id", persistent_inputs=["cfg1", "cfg2"]),
	)


async def test_persistent_with_default_does_not_block_first_run(logging_handler):
	# A persistent port whose module parameter has a default never blocks the first assembly:
	# its key is omitted (Python default applies) until it delivers a real value, mirroring default.
	# The first group emits while cfg is still absent; cfg then arrives and is replayed thereafter.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, PortTestInput({"id": 2}, delay=2), PortTestInput(EndSentinel("src"), delay=3)],
			"cfg": [PortTestInput({"opt": "late"}, delay=1), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[
			{"a": {"id": 1}},
			{"a": {"id": 2}, "cfg": {"opt": "late"}},
			EndSentinel("test"),
		],
		port_meta={"cfg": PortMeta(has_default=True)},
		config=PERSIST_CFG,
	)
	assert logging_handler.failure is False


async def test_persistent_with_default_ended_without_value_is_not_error(logging_handler):
	# A persistent port that can default and ends before delivering is not an error;
	# its key is omitted so the module's Python default applies.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"cfg": [PortTestInput(EndSentinel("src"), delay=2)],
		},
		expected_outputs=[
			{"a": {"id": 1}},
			EndSentinel("test"),
		],
		port_meta={"cfg": PortMeta(has_default=True)},
		config=PERSIST_CFG,
	)
	assert logging_handler.failure is False


async def test_required_persistent_blocks_despite_default():
	# A persistent port marked required is awaited even when it has a default, mirroring
	# DefaultContract: the complete keyed group is withheld until the value arrives.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"cfg": [PortTestInput({"opt": "X"}, delay=2), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg": {"opt": "X"}},
			EndSentinel("test"),
		],
		port_meta={"cfg": PortMeta(has_default=True, required=True)},
		config=PERSIST_CFG,
	)


async def test_default_persistent_skipped_while_blocking_on_required_one():
	# With one defaulting persistent port (never delivers) and one that must deliver late, only
	# the latter blocks emission; the defaulting port's key is omitted, the other is replayed.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1}, EndSentinel("src")],
			"cfg1": [PortTestInput(EndSentinel("src"), delay=4)],
			"cfg2": [PortTestInput({"opt": "Y"}, delay=2), PortTestInput(EndSentinel("src"), delay=3)],
		},
		expected_outputs=[
			{"a": {"id": 1}, "cfg2": {"opt": "Y"}},
			EndSentinel("test"),
		],
		port_meta={"cfg1": PortMeta(has_default=True)},
		config=KeyedJoinContract.Config(key_field="id", persistent_inputs=["cfg1", "cfg2"]),
	)


async def test_unknown_persistent_port_is_fatal(logging_handler):
	with pytest.raises(typer.Exit):
		await run_contract_scenario(
			KeyedJoinContract,
			port_inputs={"a": [{"id": 1}]},
			expected_outputs=[],
			config=KeyedJoinContract.Config(key_field="id", persistent_inputs=["missing"]),
		)


UNWRAP_CFG = KeyedJoinContract.Config(key_field="id", unwrap=True)


async def test_unwrap_delivers_inner_value():
	# Both ports carry wrappers, so the module sees the bare values and never the correlation key.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [KeyedValue(1, "A"), KeyedValue(2, "A2"), EndSentinel("src")],
			"b": [KeyedValue(1, "B"), KeyedValue(2, "B2"), EndSentinel("src")],
		},
		expected_outputs=[
			{"a": "A", "b": "B"},
			{"a": "A2", "b": "B2"},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(unwrap=True),
	)


async def test_unwrap_leaves_self_keyed_payload_whole():
	# A self-keyed record has no `value` beside its key, so it is delivered whole alongside an unwrapped port.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [Keyed(key=1, v="A"), EndSentinel("src")],
			"b": [KeyedValue(1, "B"), EndSentinel("src")],
		},
		expected_outputs=[
			{"a": Keyed(key=1, v="A"), "b": "B"},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(unwrap=True),
	)


async def test_unwrap_dict_payloads():
	# The same shape rule applies to dicts: `value` beside the key is unwrapped, any other dict is not.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1, "value": 5}, EndSentinel("src")],
			"b": [{"id": 1, "lint_ok": True}, EndSentinel("src")],
		},
		expected_outputs=[
			{"a": 5, "b": {"id": 1, "lint_ok": True}},
			EndSentinel("test"),
		],
		config=UNWRAP_CFG,
	)


async def test_unwrap_applies_to_persistent_input():
	# A persistent wrapper is unwrapped on every replay, exactly as a keyed one is.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"key": 1}, {"key": 2}, EndSentinel("src")],
			"cfg": [KeyedValue("x", "opt"), EndSentinel("src")],
		},
		expected_outputs=[
			{"a": {"key": 1}, "cfg": "opt"},
			{"a": {"key": 2}, "cfg": "opt"},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(persistent_inputs=["cfg"], unwrap=True),
	)


async def test_wrapper_delivered_intact_without_unwrap():
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [KeyedValue(1, "A"), EndSentinel("src")],
		},
		expected_outputs=[
			{"a": KeyedValue(1, "A")},
			EndSentinel("test"),
		],
		config=KeyedJoinContract.Config(),
	)


async def test_ignore_without_unwrap_warns(logging_handler):
	# The ignore list is meaningless with unwrap off; the contract says so but keeps running.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={"a": [{"id": 1}, EndSentinel("src")]},
		expected_outputs=[{"a": {"id": 1}}, EndSentinel("test")],
		config=KeyedJoinContract.Config(key_field="id", ignore=["out"]),
	)
	assert logging_handler.failure is False


# run_contract_scenario drives get_inputs() only, so output-end tests wire the ports themselves.
def build_contract(config: KeyedJoinContract.Config, port_inputs: dict[str, list[Any]]) -> tuple[KeyedJoinContract, dict[str, Port]]:
	ports = { name: Port(name=name) for name in port_inputs }
	for name, values in port_inputs.items():
		for n, val in enumerate(values):
			ports[name].queue.put_nowait(val if isinstance(val, EndSentinel) else Payload(source="test", n=n, payload=val))

	contract_ports = { name: ContractPort(name=name, get=port.get, try_get=port.try_get, has_ended=port.has_ended) for name, port in ports.items() }
	return KeyedJoinContract(id="test.contract", config=config, ports=contract_ports), ports


async def assemble(contract: KeyedJoinContract, ports: dict[str, Port]) -> Any:
	for port in ports.values():
		port.get_enabled = True
	res = await contract.get_inputs()
	for port in ports.values():
		port.get_enabled = False
	return res


async def test_process_outputs_rewraps_with_assembled_key():
	contract, ports = build_contract(UNWRAP_CFG, {"a": [{"id": 7, "value": "A"}, EndSentinel("src")]})
	await assemble(contract, ports)
	assert contract.process_outputs("out", "result") == KeyedValue(7, "result")


async def test_process_outputs_leaves_ignored_port_alone():
	# A module that keys its own fan-out emissions lists those ports in ignore.
	contract, ports = build_contract(
		KeyedJoinContract.Config(key_field="id", unwrap=True, ignore=["fanout"]),
		{"a": [{"id": 7, "value": "A"}, EndSentinel("src")]},
	)
	await assemble(contract, ports)
	assert contract.process_outputs("fanout", KeyedValue(9, "own")) == KeyedValue(9, "own")
	assert contract.process_outputs("out", "result") == KeyedValue(7, "result")


async def test_process_outputs_passes_through_without_unwrap():
	contract, ports = build_contract(CFG, {"a": [{"id": 7}, EndSentinel("src")]})
	await assemble(contract, ports)
	assert contract.process_outputs("out", "result") == "result"


async def test_process_outputs_after_end_warns_and_passes_through(logging_handler):
	# finalise() emits after termination, when no assembled key is left to attach.
	contract, ports = build_contract(UNWRAP_CFG, {"a": [{"id": 7, "value": "A"}, EndSentinel("src")]})
	await assemble(contract, ports)
	assert isinstance(await assemble(contract, ports), EndSentinel)
	assert contract.process_outputs("summary", "table") == "table"
	assert logging_handler.failure is False

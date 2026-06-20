"""Tests for KeyedJoinContract."""

import pytest
import typer

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortTestInput, PortMeta

from contracts.keyed_join import KeyedJoinContract

_CFG = KeyedJoinContract.Config(key_field="id")


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
		config=_CFG,
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
		config=_CFG,
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
		config=_CFG,
	)


async def test_blocking_await_receives_data():
	# delay=1 starts the queue empty so try_get() returns None (line 38) and
	# the contract blocks on await port.get() (lines 58-66) before the item arrives.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={"a": [PortTestInput({"id": 1}, delay=1)]},
		expected_outputs=[{"a": {"id": 1}}],
		config=_CFG,
	)


async def test_blocking_await_receives_end_sentinel():
	# EndSentinel arriving via blocking await covers lines 61-62.
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={"a": [PortTestInput(EndSentinel("src"), delay=1)]},
		expected_outputs=[EndSentinel("test")],
		config=_CFG,
	)


async def test_incomplete_key_at_stream_end_logs_error(logging_handler):
	await run_contract_scenario(
		KeyedJoinContract,
		port_inputs={
			"a": [{"id": 1, "v": "A"}, EndSentinel("src")],
			"b": [EndSentinel("src")],
		},
		expected_outputs=[EndSentinel("test")],
		config=_CFG,
	)
	assert logging_handler.failure is True


_PERSIST_CFG = KeyedJoinContract.Config(key_field="id", persistent_inputs=["cfg"])


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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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
		config=_PERSIST_CFG,
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

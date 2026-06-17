"""Unit tests for contract_default.py — is_special and DefaultContract.get_inputs."""

import pytest
import typer

from rtl_comrade.api import Payload, EndSentinel, ContractPort
from rtl_comrade.contract_default import DefaultContract, is_special
from rtl_comrade.port import Port
from rtl_comrade.testing import PortMeta, PortTestInput, run_contract_scenario


def _make_port(name, has_default=False):
	return Port(name=name, has_default=has_default)


def _make_contract_port(port: Port, required=False):
	return ContractPort(
		name=port.name,
		get=port.get,
		try_get=port.try_get,
		has_ended=port.has_ended,
		has_default=port.has_default,
		required=required,
	)


def _make_contract(ports_dict, persistent_inputs=None):
	"""ports_dict: {name: Port}. Returns (DefaultContract, contract_ports_dict)."""
	contract_ports = {name: _make_contract_port(p) for name, p in ports_dict.items()}
	config = DefaultContract.Config(persistent_inputs=persistent_inputs or [])
	return DefaultContract(id="test_node.contract", config=config, ports=contract_ports), contract_ports


# --- is_special ---


def test_is_special_required_port():
	p = _make_contract_port(_make_port("a"))
	p.state["persistent"] = False
	p.state["last_value"] = None
	assert is_special(p) is False


def test_is_special_has_default():
	p = _make_contract_port(_make_port("a", has_default=True))
	p.state["persistent"] = False
	p.state["last_value"] = None
	assert is_special(p) is True


def test_is_special_persistent_with_last_value():
	p = _make_contract_port(_make_port("a"))
	p.state["persistent"] = True
	p.state["last_value"] = Payload("src", 0, 99)
	assert is_special(p) is True


def test_is_special_persistent_no_last_value():
	p = _make_contract_port(_make_port("a"))
	p.state["persistent"] = True
	p.state["last_value"] = None
	assert is_special(p) is False


def test_is_special_required_overrides_has_default():
	p = _make_contract_port(_make_port("a", has_default=True), required=True)
	p.state["persistent"] = False
	p.state["last_value"] = None
	assert is_special(p) is False


def test_is_special_required_overrides_persistent_cached():
	p = _make_contract_port(_make_port("a"), required=True)
	p.state["persistent"] = True
	p.state["last_value"] = Payload("src", 0, 99)
	assert is_special(p) is False


# --- DefaultContract.get_inputs — required inputs ---


async def test_required_input_blocks_until_payload():
	port = _make_port("a")
	contract, _ = _make_contract({"a": port})

	payload = Payload("src", 0, 42)
	await port.queue.put(payload)
	result = await contract.get_inputs()
	assert isinstance(result, dict)
	assert result["a"] == payload


async def test_required_input_end_sentinel_returns_sentinel():
	port = _make_port("a")
	contract, _ = _make_contract({"a": port})

	await port.queue.put(EndSentinel("src"))
	result = await contract.get_inputs()
	assert isinstance(result, EndSentinel)


async def test_required_input_mixed_returns_sentinel_and_logs_error(logging_handler):
	port_a = _make_port("a")
	port_b = _make_port("b")
	contract, _ = _make_contract({"a": port_a, "b": port_b})

	await port_a.queue.put(Payload("src", 0, 1))
	await port_b.queue.put(EndSentinel("src"))
	result = await contract.get_inputs()
	assert isinstance(result, EndSentinel)
	assert logging_handler.failure is True


# --- DefaultContract.get_inputs — default inputs ---


async def test_default_input_omitted_when_empty():
	port_req = _make_port("a")
	port_def = _make_port("b", has_default=True)
	contract, _ = _make_contract({"a": port_req, "b": port_def})

	await port_req.queue.put(Payload("src", 0, 5))
	result = await contract.get_inputs()
	assert isinstance(result, dict)
	assert "b" not in result


async def test_default_input_real_payload_preferred():
	port_req = _make_port("a")
	port_def = _make_port("b", has_default=True)
	contract, _ = _make_contract({"a": port_req, "b": port_def})

	real_payload = Payload("upstream", 0, 99)
	await port_req.queue.put(Payload("src", 0, 1))
	await port_def.queue.put(real_payload)
	result = await contract.get_inputs()
	assert result["b"] == real_payload


async def test_default_input_omitted_after_ended():
	port_req = _make_port("a")
	port_def = _make_port("b", has_default=True)
	contract, _ = _make_contract({"a": port_req, "b": port_def})

	await port_def.queue.put(EndSentinel("up"))
	port_def.try_get()  # consume sentinel so has_ended() returns True
	assert port_def.has_ended() is True

	await port_req.queue.put(Payload("src", 0, 1))
	result = await contract.get_inputs()
	assert isinstance(result, dict)
	assert "b" not in result


async def test_default_input_omitted_on_repeated_calls():
	port_req = _make_port("a")
	port_def = _make_port("b", has_default=True)
	contract, _ = _make_contract({"a": port_req, "b": port_def})

	for i in range(3):
		await port_req.queue.put(Payload("src", i, i))
		result = await contract.get_inputs()
		assert "b" not in result


# --- DefaultContract.get_inputs — persistent inputs ---


async def test_persistent_input_reuses_last_value():
	port_val = _make_port("value")
	port_mul = _make_port("multiplier")
	contract, _ = _make_contract(
		{"value": port_val, "multiplier": port_mul},
		persistent_inputs=["multiplier"],
	)

	# First invocation: supply both
	await port_val.queue.put(Payload("src", 0, 1))
	await port_mul.queue.put(Payload("src", 0, 5))
	result1 = await contract.get_inputs()
	assert result1["multiplier"].payload == 5

	# Second invocation: only value; multiplier should reuse last_value
	await port_val.queue.put(Payload("src", 1, 2))
	result2 = await contract.get_inputs()
	assert result2["multiplier"].payload == 5


async def test_persistent_input_updates_on_new_payload():
	port_val = _make_port("value")
	port_mul = _make_port("multiplier")
	contract, _ = _make_contract(
		{"value": port_val, "multiplier": port_mul},
		persistent_inputs=["multiplier"],
	)

	await port_val.queue.put(Payload("src", 0, 1))
	await port_mul.queue.put(Payload("src", 0, 5))
	await contract.get_inputs()

	# Second call: new multiplier value queued
	await port_val.queue.put(Payload("src", 1, 2))
	await port_mul.queue.put(Payload("src", 1, 9))
	result = await contract.get_inputs()
	assert result["multiplier"].payload == 9


def test_persistent_input_unknown_port_fatal(logging_handler):
	port = _make_port("value")
	with pytest.raises(typer.Exit):
		_make_contract({"value": port}, persistent_inputs=["nonexistent"])


# --- multi-call scenarios via harness ---


async def test_two_required_ports_full_sequence():
	await run_contract_scenario(
		DefaultContract,
		port_inputs={
			"x": [1, 2, EndSentinel("src")],
			"y": [10, 20, EndSentinel("src")],
		},
		expected_outputs=[
			{"x": 1, "y": 10},
			{"x": 2, "y": 20},
			EndSentinel("test"),
		],
		config=DefaultContract.Config(),
	)


async def test_default_port_real_value_then_omitted():
	# "b" supplies one real value then runs dry; subsequent calls omit "b" from the result.
	await run_contract_scenario(
		DefaultContract,
		port_inputs={
			"a": [1, 2, EndSentinel("src")],
			"b": [99],
		},
		expected_outputs=[
			{"a": 1, "b": 99},
			{"a": 2},
			EndSentinel("test"),
		],
		port_meta={"b": PortMeta(has_default=True)},
		config=DefaultContract.Config(),
	)


async def test_persistent_port_with_default_omitted_when_no_last_value():
	# Persistent port that also has a default but has never received a real value:
	# is_special() is True (has_default), try_get() returns None, last_value is None,
	# so the key is omitted and Python's default activates.
	port_req = _make_port("a")
	port_mul = _make_port("multiplier", has_default=True)
	contract, _ = _make_contract(
		{"a": port_req, "multiplier": port_mul},
		persistent_inputs=["multiplier"],
	)
	await port_req.queue.put(Payload("src", 0, 1))
	result = await contract.get_inputs()
	assert "multiplier" not in result
	assert contract.ports["multiplier"].state["last_value"] is None


async def test_default_port_ended_omitted_from_result():
	# A default-only port that has ended: key is omitted from the result dict.
	port_req = _make_port("a")
	port_def = _make_port("b", has_default=True)
	contract, _ = _make_contract({"a": port_req, "b": port_def})

	await port_def.queue.put(EndSentinel("upstream"))
	port_def.try_get()  # consume sentinel → ended=True
	assert port_def.has_ended() is True

	await port_req.queue.put(Payload("src", 0, 1))
	result = await contract.get_inputs()
	assert isinstance(result, dict)
	assert "b" not in result


async def test_required_default_port_blocks_for_payload():
	# "b" has a default but is marked required, so the contract must await a real value
	# delivered after it has started running rather than omitting the key. The sentinels
	# are delayed past the value so the first call pairs a real "b" with "a".
	await run_contract_scenario(
		DefaultContract,
		port_inputs={
			"a": [1, PortTestInput(EndSentinel("src"), delay=2)],
			"b": [PortTestInput(99, delay=1), PortTestInput(EndSentinel("src"), delay=2)],
		},
		expected_outputs=[
			{"a": 1, "b": 99},
			EndSentinel("test"),
		],
		port_meta={"b": PortMeta(has_default=True, required=True)},
		config=DefaultContract.Config(),
	)


async def test_persistent_port_updates_eagerly_then_reuses():
	# "scale" is consumed as a required input on call 1, updated eagerly on call 2
	# when a new value is already queued, then reused from cache on call 3.
	await run_contract_scenario(
		DefaultContract,
		port_inputs={
			"value": [1, 2, 3, EndSentinel("src")],
			"scale": [10, 30],
		},
		expected_outputs=[
			{"value": 1, "scale": 10},
			{"value": 2, "scale": 30},
			{"value": 3, "scale": 30},
			EndSentinel("test"),
		],
		config=DefaultContract.Config(persistent_inputs=["scale"]),
	)

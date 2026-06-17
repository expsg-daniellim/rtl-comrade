"""Contract testing harness.

Provides run_contract_scenario() so contract authors can test scheduling
logic in isolation from the full graph runtime.

Usage::

	from rtl_comrade.testing import run_contract_scenario, PortTestInput
	from rtl_comrade.api import EndSentinel

	# All items pre-enqueued (default, delay=0):
	await run_contract_scenario(
		MyContract,
		port_inputs={"a": [1, 2, EndSentinel("src")]},
		expected_outputs=[{"a": 1}, {"a": 2}, EndSentinel("src")],
		config=MyContract.Config(),
	)

	# Item delivered asynchronously after the contract has started running:
	await run_contract_scenario(
		MyContract,
		port_inputs={"a": [PortTestInput(1, delay=1), PortTestInput(EndSentinel("src"), delay=2)]},
		expected_outputs=[{"a": 1}, EndSentinel("src")],
		config=MyContract.Config(),
	)
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass
from typing import Any

import pytest
import structlog

from .api import ContractPort, EndSentinel, Payload
from .logging import initialise_logging
from .port import Port


@pytest.fixture
def logging_handler():
	"""Pytest fixture that installs the rtl-comrade log handler for the duration of a test.

	Fatal log calls (CRITICAL) raise SystemExit(1). Error log calls set
	handler.failure = True without raising. Both are reset after each test.
	"""
	structlog.reset_defaults()
	handler, _ = initialise_logging(logging.DEBUG)
	yield handler
	logging.getLogger().handlers.clear()
	structlog.reset_defaults()


@dataclass
class PortMeta:
	"""Per-port metadata applied when the harness constructs test Port objects.

	Attributes:
		has_default: Whether the port should report a default value.
		required: Whether the port is marked required, forcing the default contract to
			await a real value even when has_default is set.
	"""

	has_default: bool = False
	required: bool = False


@dataclass
class PortTestInput:
	"""A single item in a port's input list, with an optional delivery delay.

	Attributes:
		value: The value to deliver — raw Python value, Payload, or EndSentinel.
			Raw values are wrapped in Payload(source="test", ...) exactly as
			bare list items are.
		delay: Number of asyncio.sleep(0) yields to wait before delivering this
			item. delay=0 (default) pre-enqueues the item before get_inputs() is
			called. delay=N delivers the item after N yields while the contract is
			already running, allowing tests to exercise blocking-await paths.
	"""

	value: Any
	delay: int = 0


async def run_contract_scenario(
	contract_cls: type,
	port_inputs: dict[str, list[Any]],
	expected_outputs: list[dict[str, Any] | EndSentinel],
	*,
	port_meta: dict[str, PortMeta] | None = None,
	config: Any = None,
	contract_id: str = "test.contract",
	timeout: float = 5.0,
) -> None:
	"""Test a contract by feeding it port data and asserting get_inputs() outputs.

	The harness creates one Port per key in port_inputs, enqueues items according
	to their delay, instantiates the contract, then calls get_inputs() once per
	entry in expected_outputs and asserts the result matches.

	Args:
		contract_cls: The contract class to test.
		port_inputs: Maps each port name to a list of values to deliver. Each
			item may be a raw Python value, a Payload, an EndSentinel, or a
			PortTestInput. Raw values and Payload/EndSentinel instances are treated
			as PortTestInput(value, delay=0). delay=0 items are pre-enqueued before
			get_inputs() is called; delay=N items are delivered after N
			asyncio.sleep(0) yields while the contract is already running.
		expected_outputs: One entry per get_inputs() call. Each entry is either:
			- dict[str, Any]: maps port name to the expected .payload value
			- EndSentinel class or instance: asserts the call returns an EndSentinel
		port_meta: Optional per-port Port constructor overrides, e.g.
			{"b": PortMeta(has_default=True)}.
		config: Passed to contract __init__ only when the parameter is declared.
		contract_id: The id string passed to the contract.
		timeout: Maximum seconds to wait for each get_inputs() call.

	Raises:
		AssertionError: When an actual get_inputs() result does not match expected.
		asyncio.TimeoutError: When a get_inputs() call exceeds timeout.
	"""
	meta = port_meta or {}
	_default_meta = PortMeta()

	ports: dict[str, Port] = {
		name: Port(
			name=name,
			has_default=meta.get(name, _default_meta).has_default,
		)
		for name in port_inputs
	}

	# Normalise every item and split by delay.
	n_counters: dict[str, int] = {name: 0 for name in port_inputs}
	deferred: list[tuple[str, int, Payload | EndSentinel]] = []

	for name, values in port_inputs.items():
		for val in values:
			pti = val if isinstance(val, PortTestInput) else PortTestInput(val)
			item = _wrap_item(pti.value, name, n_counters)
			if pti.delay == 0:
				ports[name].queue.put_nowait(item)
			else:
				deferred.append((name, pti.delay, item))

	contract_ports: dict[str, ContractPort] = {
		name: ContractPort(
			name=name,
			get=port.get,
			try_get=port.try_get,
			has_ended=port.has_ended,
			has_default=port.has_default,
			required=meta.get(name, _default_meta).required,
		)
		for name, port in ports.items()
	}

	sig = _validate_contract(contract_cls)
	kwargs: dict[str, Any] = {}
	if "id" in sig.parameters:
		kwargs["id"] = contract_id
	if "ports" in sig.parameters:
		kwargs["ports"] = contract_ports
	if "config" in sig.parameters and config is not None:
		kwargs["config"] = config
	contract = contract_cls(**kwargs)

	if deferred:
		await asyncio.gather(
			_contract_loop(contract, expected_outputs, timeout),
			_feeder(ports, deferred),
		)
	else:
		await _contract_loop(contract, expected_outputs, timeout)


def _wrap_item(val: Any, name: str, n_counters: dict[str, int]) -> Payload | EndSentinel:
	if isinstance(val, (Payload, EndSentinel)):
		return val
	item = Payload(source="test", n=n_counters[name], payload=val)
	n_counters[name] += 1
	return item


async def _contract_loop(
	contract: Any,
	expected_outputs: list[Any],
	timeout: float,
) -> None:
	for step, expected in enumerate(expected_outputs):
		if inspect.iscoroutinefunction(contract.get_inputs):
			actual = await asyncio.wait_for(contract.get_inputs(), timeout=timeout)
		else:
			actual = contract.get_inputs()
		_assert_step(step, actual, expected)


async def _feeder(
	ports: dict[str, Port],
	deferred: list[tuple[str, int, Payload | EndSentinel]],
) -> None:
	max_delay = max(delay for _, delay, _ in deferred)
	for tick in range(1, max_delay + 1):
		await asyncio.sleep(0)
		for name, delay, item in deferred:
			if delay == tick:
				ports[name].queue.put_nowait(item)


def _validate_contract(contract_cls: type) -> inspect.Signature:
	assert hasattr(contract_cls, 'get_inputs'), (
		f"{contract_cls.__name__} must expose get_inputs"
	)
	try:
		sig = inspect.signature(contract_cls.__init__)
	except (TypeError, ValueError) as e:
		raise AssertionError(
			f"{contract_cls.__name__}.__init__ signature is not inspectable: {e}"
		) from e
	assert 'ports' in sig.parameters, (
		f"{contract_cls.__name__}.__init__ does not declare 'ports' — contract cannot read inputs"
	)
	return sig


def _assert_step(step: int, actual: Any, expected: Any) -> None:
	is_sentinel_expected = isinstance(expected, EndSentinel)

	if is_sentinel_expected:
		assert isinstance(actual, EndSentinel), (
			f"step {step}: expected EndSentinel, got {actual!r}"
		)
		return

	assert isinstance(actual, dict), f"step {step}: expected dict, got {actual!r}"
	assert set(actual.keys()) == set(expected.keys()), (
		f"step {step}: port name mismatch — got {set(actual.keys())!r}, expected {set(expected.keys())!r}"
	)
	for port_name, exp_val in expected.items():
		actual_payload = actual[port_name]
		assert isinstance(actual_payload, Payload), (
			f"step {step}, port '{port_name}': expected Payload, got {actual_payload!r}"
		)
		assert actual_payload.payload == exp_val, (
			f"step {step}, port '{port_name}': expected .payload={exp_val!r}, got .payload={actual_payload.payload!r}"
		)


# ---------------------------------------------------------------------------
# Module testing harness
# ---------------------------------------------------------------------------

def _collect_module_result(res: Any, collected: dict[str, list[Any]]) -> None:
	"""Normalize one module output and append it to the collected emissions dict.

	Mirrors Node.process_result() but raises AssertionError on malformed output
	instead of logging, making test failures explicit.
	"""
	if res is None:
		return
	if isinstance(res, tuple):
		assert len(res) == 2, (
			f"module emitted a malformed tuple of length {len(res)}: {res!r} "
			f"(expected (str, value))"
		)
		port, value = res
		assert isinstance(port, str), (
			f"module emitted a tuple with non-string port name {port!r} "
			f"(type {type(port).__name__})"
		)
	else:
		port, value = "default", res
	collected.setdefault(port, []).append(value)


def _validate_module(module_cls: type) -> inspect.Signature:
	assert hasattr(module_cls, "run"), (
		f"{module_cls.__name__} must expose run"
	)
	try:
		sig = inspect.signature(module_cls.__init__)
	except (TypeError, ValueError) as e:
		raise AssertionError(
			f"{module_cls.__name__}.__init__ signature is not inspectable: {e}"
		) from e
	return sig


def _assert_module_emissions(
	collected: dict[str, list[Any]],
	expected: dict[str, list[Any]],
) -> None:
	unexpected = set(collected.keys()) - set(expected.keys())
	assert not unexpected, (
		f"unexpected emissions on port(s) {sorted(unexpected)!r}: "
		+ ", ".join(f"{p!r}: {collected[p]!r}" for p in sorted(unexpected))
	)
	for port_name, exp_values in expected.items():
		actual_values = collected.get(port_name, [])
		assert len(actual_values) == len(exp_values), (
			f"port {port_name!r}: expected {len(exp_values)} emission(s), "
			f"got {len(actual_values)}: {actual_values!r}"
		)
		for i, (actual_val, exp_val) in enumerate(zip(actual_values, exp_values)):
			assert actual_val == exp_val, (
				f"port {port_name!r}, emission[{i}]: expected {exp_val!r}, got {actual_val!r}"
			)


async def run_module_scenario(
	module_cls: type,
	input_sequence: list[dict[str, Any]],
	expected_emissions: dict[str, list[Any]],
	*,
	config: Any = None,
	module_id: str = "test.module",
	timeout: float = 5.0,
) -> None:
	"""Test a module by driving its run() with a sequence of input dicts and
	asserting the collected emissions match expected_emissions.

	Args:
		module_cls: The module class to test.
		input_sequence: One dict per run() invocation; keys are port/parameter
			names, values are raw Python values (not Payload-wrapped).
		expected_emissions: Maps port name to an ordered list of expected emitted
			values. Ports absent from this dict are expected to produce zero
			emissions.
		config: Passed to module __init__ only when the parameter is declared.
			Passed as-is (not deserialized via serde).
		module_id: The id string passed to the module when its __init__ accepts one.
		timeout: Maximum seconds to wait for each async run() call.

	Raises:
		AssertionError: When emissions do not match expected_emissions, or when
			the module emits a malformed tuple.
		asyncio.TimeoutError: When an async run() call exceeds timeout.
	"""
	sig = _validate_module(module_cls)

	kwargs: dict[str, Any] = {}
	if "id" in sig.parameters:
		kwargs["id"] = module_id
	if "config" in sig.parameters and config is not None:
		kwargs["config"] = config
	module = module_cls(**kwargs)

	collected: dict[str, list[Any]] = {}

	for inputs in input_sequence:
		if inspect.iscoroutinefunction(module.run):
			res = await asyncio.wait_for(module.run(**inputs), timeout=timeout)
		else:
			res = module.run(**inputs)

		if inspect.isasyncgen(res):
			async for r in res:
				_collect_module_result(r, collected)
		elif inspect.isgenerator(res):
			for r in res:
				_collect_module_result(r, collected)
		else:
			_collect_module_result(res, collected)

		if len(inputs) == 0:
			break

	_assert_module_emissions(collected, expected_emissions)

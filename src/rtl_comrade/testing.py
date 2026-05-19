"""Contract testing harness.

Provides run_contract_scenario() so contract authors can test scheduling
logic in isolation from the full graph runtime.

Usage::

    from rtl_comrade.testing import run_contract_scenario
    from rtl_comrade.api import EndSentinel

    await run_contract_scenario(
        MyContract,
        port_inputs={"a": [1, 2, EndSentinel("src")]},
        expected_outputs=[{"a": 1}, {"a": 2}, EndSentinel],
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
    handler = initialise_logging(logging.DEBUG)
    yield handler
    logging.getLogger().handlers.clear()
    structlog.reset_defaults()


@dataclass
class PortMeta:
    """Per-port metadata applied when the harness constructs test Port objects.

    Attributes:
        has_default: Whether the port should report a default value.
        default: The raw default value for the port, if any.
    """

    has_default: bool = False
    default: Any = None


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

    The harness creates one Port per key in port_inputs, pre-enqueues all data,
    instantiates the contract, then calls get_inputs() once per entry in
    expected_outputs and asserts the result matches.

    Args:
        contract_cls: The contract class to test.
        port_inputs: Maps each port name to a list of values to enqueue.
            Raw Python values are wrapped in Payload(source="test", n=<index>,
            payload=val). Pass Payload or EndSentinel instances to override.
        expected_outputs: One entry per get_inputs() call. Each entry is either:
            - dict[str, Any]: maps port name to the expected .payload value
            - EndSentinel class or instance: asserts the call returns an EndSentinel
        port_meta: Optional per-port Port constructor overrides, e.g.
            {"b": PortMeta(has_default=True, default=0)}.
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
            default=meta.get(name, _default_meta).default,
        )
        for name in port_inputs
    }

    for name, values in port_inputs.items():
        port = ports[name]
        for i, val in enumerate(values):
            item = val if isinstance(val, (Payload, EndSentinel)) else Payload(source="test", n=i, payload=val)
            port.queue.put_nowait(item)

    contract_ports: dict[str, ContractPort] = {
        name: ContractPort(
            name=name,
            get=port.get,
            try_get=port.try_get,
            has_ended=port.has_ended,
            has_default=port.has_default,
            default=port.default,
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

    for step, expected in enumerate(expected_outputs):
        if inspect.iscoroutinefunction(contract.get_inputs):
            actual = await asyncio.wait_for(contract.get_inputs(), timeout=timeout)
        else:
            actual = contract.get_inputs()
        _assert_step(step, actual, expected)


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
    is_sentinel_expected = expected is EndSentinel or isinstance(expected, EndSentinel)

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

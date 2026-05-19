"""Tests for the contract testing harness, using DefaultContract as subject."""

import asyncio
import inspect
from unittest.mock import patch

import pytest

from rtl_comrade.api import ContractPort, EndSentinel
from rtl_comrade.contract_default import DefaultContract
from rtl_comrade.testing import run_contract_scenario, PortMeta, run_module_scenario


async def test_required_port_single_value():
    await run_contract_scenario(
        DefaultContract,
        port_inputs={"a": [42, EndSentinel("src")]},
        expected_outputs=[{"a": 42}, EndSentinel],
        config=DefaultContract.Config(),
    )


async def test_default_port_synthesized_when_queue_empty():
    # "b" queue is empty; DefaultContract synthesizes a payload from its default value.
    await run_contract_scenario(
        DefaultContract,
        port_inputs={"a": [1, EndSentinel("src")], "b": []},
        expected_outputs=[{"a": 1, "b": 0}, EndSentinel],
        port_meta={"b": PortMeta(has_default=True, default=0)},
        config=DefaultContract.Config(),
    )


async def test_persistent_port_value_reused():
    # "b" supplies one value; on the second call it is reused from cache.
    await run_contract_scenario(
        DefaultContract,
        port_inputs={"a": [100, 200, EndSentinel("src")], "b": [10]},
        expected_outputs=[{"a": 100, "b": 10}, {"a": 200, "b": 10}, EndSentinel],
        config=DefaultContract.Config(persistent_inputs=["b"]),
    )


# --- validation checks ---

def test_validation_rejects_missing_get_inputs():
    class NoGetInputs:
        def __init__(self, ports: dict[str, ContractPort]):
            pass

    with pytest.raises(AssertionError, match="must expose get_inputs"):
        import asyncio
        asyncio.run(run_contract_scenario(NoGetInputs, port_inputs={}, expected_outputs=[]))


def test_validation_rejects_missing_ports_parameter():
    class NoPorts:
        def __init__(self):
            pass
        def get_inputs(self):
            return {}

    with pytest.raises(AssertionError, match="does not declare 'ports'"):
        asyncio.run(run_contract_scenario(NoPorts, port_inputs={}, expected_outputs=[]))


async def test_sync_contract_get_inputs_invoked():
    # Covers the `else: actual = contract.get_inputs()` branch in _contract_loop
    # when the contract's get_inputs is a plain synchronous method.
    class _SyncContract:
        def __init__(self, ports):
            self.ports = ports
            self._done = False

        def get_inputs(self):
            if self._done:
                return EndSentinel("sync.contract")
            self._done = True
            return {}

    await run_contract_scenario(
        _SyncContract,
        port_inputs={},
        expected_outputs=[{}, EndSentinel],
    )


def test_validate_contract_uninspectable_init_raises():
    class _C:
        def __init__(self, ports):
            self.ports = ports
        def get_inputs(self):
            return {}

    with patch.object(inspect, "signature", side_effect=TypeError("uninspectable")):
        with pytest.raises(AssertionError, match="not inspectable"):
            asyncio.run(run_contract_scenario(_C, port_inputs={}, expected_outputs=[]))


def test_validate_module_uninspectable_init_raises():
    class _M:
        def run(self):
            pass

    with patch.object(inspect, "signature", side_effect=TypeError("uninspectable")):
        with pytest.raises(AssertionError, match="not inspectable"):
            asyncio.run(run_module_scenario(_M, input_sequence=[], expected_emissions={}))

"""Tests for KeyedJoinContract."""

import pytest

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortTestInput

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
            EndSentinel,
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
            EndSentinel,
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
            EndSentinel,
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
        expected_outputs=[EndSentinel],
        config=_CFG,
    )


async def test_incomplete_key_at_stream_end_logs_error(logging_handler):
    await run_contract_scenario(
        KeyedJoinContract,
        port_inputs={
            "a": [{"id": 1, "v": "A"}, EndSentinel("src")],
            "b": [EndSentinel("src")],
        },
        expected_outputs=[EndSentinel],
        config=_CFG,
    )
    assert logging_handler.failure is True

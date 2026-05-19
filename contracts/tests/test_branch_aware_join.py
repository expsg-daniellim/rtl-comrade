"""Tests for BranchAwareJoinContract."""

import pytest

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario, PortTestInput

from contracts.branch_aware_join import BranchAwareJoinContract
from contracts.sentinels import BranchSkip

_CFG = BranchAwareJoinContract.Config(key_field="id")


async def test_both_ports_present():
    await run_contract_scenario(
        BranchAwareJoinContract,
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


async def test_one_port_skipped():
    await run_contract_scenario(
        BranchAwareJoinContract,
        port_inputs={
            "a": [{"id": 1, "v": "A"}, EndSentinel("src")],
            "b": [BranchSkip(key=1), EndSentinel("src")],
        },
        expected_outputs=[
            {"a": {"id": 1, "v": "A"}},
            EndSentinel,
        ],
        config=_CFG,
    )


async def test_multiple_keys_with_mixed_skips():
    await run_contract_scenario(
        BranchAwareJoinContract,
        port_inputs={
            "a": [{"id": 1}, BranchSkip(key=2), EndSentinel("src")],
            "b": [BranchSkip(key=1), {"id": 2}, EndSentinel("src")],
        },
        expected_outputs=[
            {"a": {"id": 1}},
            {"b": {"id": 2}},
            EndSentinel,
        ],
        config=_CFG,
    )


async def test_blocking_await_receives_data():
    # delay=1 starts the queue empty so try_get() returns None (line 37) and
    # the contract blocks on await port.get() (lines 59-67) before the item arrives.
    await run_contract_scenario(
        BranchAwareJoinContract,
        port_inputs={"a": [PortTestInput({"id": 1}, delay=1)]},
        expected_outputs=[{"a": {"id": 1}}],
        config=_CFG,
    )


async def test_blocking_await_receives_end_sentinel():
    # EndSentinel arriving via blocking await covers lines 62-63.
    await run_contract_scenario(
        BranchAwareJoinContract,
        port_inputs={"a": [PortTestInput(EndSentinel("src"), delay=1)]},
        expected_outputs=[EndSentinel],
        config=_CFG,
    )


async def test_end_sentinel_returns_sentinel():
    await run_contract_scenario(
        BranchAwareJoinContract,
        port_inputs={
            "a": [EndSentinel("src")],
            "b": [EndSentinel("src")],
        },
        expected_outputs=[EndSentinel],
        config=_CFG,
    )

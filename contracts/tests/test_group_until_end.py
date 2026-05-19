"""Tests for GroupUntilEndContract."""

import pytest

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario

from contracts.group_until_end import GroupUntilEndContract
from contracts.sentinels import GroupEnd


async def test_single_group_single_port():
    await run_contract_scenario(
        GroupUntilEndContract,
        port_inputs={"a": [1, 2, GroupEnd(), EndSentinel("src")]},
        expected_outputs=[{"a": [1, 2]}, EndSentinel],
    )


async def test_single_group_multiple_ports():
    await run_contract_scenario(
        GroupUntilEndContract,
        port_inputs={
            "a": [1, 2, GroupEnd(), EndSentinel("src")],
            "b": [3, GroupEnd(), EndSentinel("src")],
        },
        expected_outputs=[{"a": [1, 2], "b": [3]}, EndSentinel],
    )


async def test_multiple_groups():
    await run_contract_scenario(
        GroupUntilEndContract,
        port_inputs={
            "a": [1, GroupEnd(), 3, GroupEnd(), EndSentinel("src")],
            "b": [2, GroupEnd(), 4, GroupEnd(), EndSentinel("src")],
        },
        expected_outputs=[
            {"a": [1], "b": [2]},
            {"a": [3], "b": [4]},
            EndSentinel,
        ],
    )


async def test_end_sentinel_mid_group_returns_sentinel():
    await run_contract_scenario(
        GroupUntilEndContract,
        port_inputs={"a": [1, 2, EndSentinel("src")]},
        expected_outputs=[EndSentinel],
    )


async def test_empty_group():
    await run_contract_scenario(
        GroupUntilEndContract,
        port_inputs={"a": [GroupEnd(), EndSentinel("src")]},
        expected_outputs=[{"a": []}, EndSentinel],
    )

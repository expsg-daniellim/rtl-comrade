"""Tests for LatestContract."""

import pytest

from rtl_comrade.api import EndSentinel
from rtl_comrade.testing import run_contract_scenario

from contracts.latest import LatestContract

_CFG = LatestContract.Config(trigger_ports=["trigger"])


async def test_trigger_uses_latest_state():
    await run_contract_scenario(
        LatestContract,
        port_inputs={
            "state": [10, EndSentinel("src")],
            "trigger": [1, EndSentinel("src")],
        },
        expected_outputs=[
            {"state": 10, "trigger": 1},
            EndSentinel,
        ],
        config=_CFG,
    )


async def test_multiple_triggers_reuse_state():
    await run_contract_scenario(
        LatestContract,
        port_inputs={
            "state": [10, EndSentinel("src")],
            "trigger": [1, 2, EndSentinel("src")],
        },
        expected_outputs=[
            {"state": 10, "trigger": 1},
            {"state": 10, "trigger": 2},
            EndSentinel,
        ],
        config=_CFG,
    )


async def test_state_updates_before_trigger():
    await run_contract_scenario(
        LatestContract,
        port_inputs={
            "state": [10, 20, EndSentinel("src")],
            "trigger": [1, 2, EndSentinel("src")],
        },
        expected_outputs=[
            {"state": 20, "trigger": 1},
            {"state": 20, "trigger": 2},
            EndSentinel,
        ],
        config=_CFG,
    )


async def test_trigger_port_end_returns_sentinel():
    await run_contract_scenario(
        LatestContract,
        port_inputs={
            "state": [10, EndSentinel("src")],
            "trigger": [EndSentinel("src")],
        },
        expected_outputs=[EndSentinel],
        config=_CFG,
    )

"""Unit tests for api.py — Payload, EndSentinel, ContractPort, NoDefaultError."""

import pytest
from dataclasses import FrozenInstanceError

from rtl_comrade.api import Payload, EndSentinel, ContractPort, NoDefaultError


# --- Payload ---

def test_payload_frozen():
    p = Payload("src", 0, "data")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        p.source = "other"


def test_payload_fields():
    p = Payload("node_a", 7, 99)
    assert p.source == "node_a"
    assert p.n == 7
    assert p.payload == 99


def test_payload_equality():
    assert Payload("a", 0, 1) == Payload("a", 0, 1)
    assert Payload("a", 0, 1) != Payload("a", 1, 1)


# --- EndSentinel ---

def test_end_sentinel_frozen():
    s = EndSentinel("src")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        s.source = "other"


def test_end_sentinel_source():
    s = EndSentinel("upstream")
    assert s.source == "upstream"


# --- ContractPort.get_default_payload ---

def _stub_contract_port(name, has_default=True, default=42):
    return ContractPort(
        name=name,
        get=None,
        try_get=None,
        has_ended=None,
        has_default=has_default,
        default=default,
    )


def test_get_default_payload_first_call():
    port = _stub_contract_port("x", has_default=True, default=42)
    p = port.get_default_payload()
    assert p.source == "_default"
    assert p.n == 0
    assert p.payload == 42


def test_get_default_payload_increments_n():
    port = _stub_contract_port("x", has_default=True, default=7)
    p0 = port.get_default_payload()
    p1 = port.get_default_payload()
    p2 = port.get_default_payload()
    assert p0.n == 0
    assert p1.n == 1
    assert p2.n == 2


def test_get_default_payload_no_default_raises():
    port = _stub_contract_port("myport", has_default=False, default=None)
    with pytest.raises(NoDefaultError) as exc_info:
        port.get_default_payload()
    assert exc_info.value.name == "myport"


# --- NoDefaultError ---

def test_no_default_error_is_exception():
    e = NoDefaultError("port_x")
    assert isinstance(e, Exception)
    assert e.name == "port_x"


def test_no_default_error_frozen():
    e = NoDefaultError("p")
    with pytest.raises((FrozenInstanceError, AttributeError)):
        e.name = "other"

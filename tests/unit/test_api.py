"""Unit tests for api.py — Payload, EndSentinel, ContractPort."""

import pytest
from dataclasses import FrozenInstanceError

from rtl_comrade.api import Payload, EndSentinel, ContractPort


# --- Payload ---


def test_payload_frozen():
	p = Payload("src", 0, "data")
	with pytest.raises((FrozenInstanceError, AttributeError)):
		p.source = "other"  # ty: ignore[invalid-assignment] — intentionally mutating a frozen dataclass to verify it raises


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
		s.source = "other"  # ty: ignore[invalid-assignment] — intentionally mutating a frozen dataclass to verify it raises


def test_end_sentinel_source():
	s = EndSentinel("upstream")
	assert s.source == "upstream"



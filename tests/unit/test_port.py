"""Unit tests for port.py — Port and InvalidEnqueuedError."""

import asyncio
import pytest

from rtl_comrade.port import Port, IllegalGetAccessError, InvalidEnqueuedError
from rtl_comrade.api import Payload, EndSentinel
from rtl_comrade.structure import ModuleStructureArg


# --- Port.from_structure ---


def test_from_structure_copies_fields():
	arg = ModuleStructureArg(name="val", param="val", has_default=True)
	p = Port.from_structure(arg)
	assert p.name == "val"
	assert p.param == "val"
	assert p.has_default is True
	assert p.queue.empty()


def test_from_structure_carries_param():
	arg = ModuleStructureArg(name="list", param="list_")
	p = Port.from_structure(arg)
	assert p.name == "list"
	assert p.param == "list_"


def test_param_defaults_to_name():
	assert Port(name="a").param == "a"


def test_from_structure_no_default():
	arg = ModuleStructureArg(name="a", param="a")
	p = Port.from_structure(arg)
	assert p.has_default is False


# --- Port.get ---


async def test_get_returns_payload():
	p = Port(name="a", get_enabled=True)
	payload = Payload("src", 0, "hello")
	await p.queue.put(payload)
	result = await p.get()
	assert result == payload
	assert p.ended is False


async def test_get_end_sentinel_sets_ended():
	p = Port(name="a", get_enabled=True)
	sentinel = EndSentinel("src")
	await p.queue.put(sentinel)
	result = await p.get()
	assert result == sentinel
	assert p.ended is True


async def test_get_invalid_type_raises():
	p = Port(name="myport", get_enabled=True)
	await p.queue.put("not_a_payload")  # ty: ignore[invalid-argument-type] — deliberately enqueuing a bad type to verify InvalidEnqueuedError is raised
	with pytest.raises(InvalidEnqueuedError) as exc_info:
		await p.get()
	assert exc_info.value.name == "myport"
	assert exc_info.value.type_ == "str"


async def test_get_blocks_on_empty():
	p = Port(name="a", get_enabled=True)
	with pytest.raises(asyncio.TimeoutError):
		await asyncio.wait_for(p.get(), timeout=0.05)


# --- Port.try_get ---


def test_try_get_empty_returns_none():
	p = Port(name="a", get_enabled=True)
	assert p.try_get() is None


async def test_try_get_returns_payload():
	p = Port(name="a", get_enabled=True)
	payload = Payload("src", 0, 42)
	await p.queue.put(payload)
	result = p.try_get()
	assert result == payload
	assert p.ended is False


async def test_try_get_end_sentinel_sets_ended():
	p = Port(name="a", get_enabled=True)
	sentinel = EndSentinel("src")
	await p.queue.put(sentinel)
	result = p.try_get()
	assert result == sentinel
	assert p.ended is True


async def test_try_get_after_ended_returns_none():
	p = Port(name="a", get_enabled=True)
	await p.queue.put(EndSentinel("src"))
	p.try_get()  # consume sentinel, sets ended=True
	# Now try_get on an ended port returns None without touching queue
	result = p.try_get()
	assert result is None


async def test_try_get_invalid_raises():
	p = Port(name="bad", get_enabled=True)
	await p.queue.put(12345)  # ty: ignore[invalid-argument-type] — deliberately enqueuing a bad type to verify InvalidEnqueuedError is raised
	with pytest.raises(InvalidEnqueuedError) as exc_info:
		p.try_get()
	assert exc_info.value.name == "bad"
	assert exc_info.value.type_ == "int"


# --- Port.has_ended ---


def test_has_ended_initially_false():
	p = Port(name="a")
	assert p.has_ended() is False


async def test_has_ended_true_after_get_sentinel():
	p = Port(name="a", get_enabled=True)
	await p.queue.put(EndSentinel("src"))
	await p.get()
	assert p.has_ended() is True


async def test_has_ended_true_after_try_get_sentinel():
	p = Port(name="a", get_enabled=True)
	await p.queue.put(EndSentinel("src"))
	p.try_get()
	assert p.has_ended() is True


# --- The read window ---


def test_get_enabled_defaults_false():
	assert Port(name="a").get_enabled is False


async def test_get_disabled_raises_and_leaves_queue():
	p = Port(name="a")
	await p.queue.put(Payload("src", 0, "hello"))
	with pytest.raises(IllegalGetAccessError) as exc_info:
		await p.get()
	assert exc_info.value.name == "a"
	assert exc_info.value.type_ == "get"
	assert p.queue.qsize() == 1  # rejected read consumes nothing


async def test_try_get_disabled_raises_and_leaves_queue():
	p = Port(name="a")
	await p.queue.put(Payload("src", 0, "hello"))
	with pytest.raises(IllegalGetAccessError) as exc_info:
		p.try_get()
	assert exc_info.value.name == "a"
	assert exc_info.value.type_ == "try_get"
	assert p.queue.qsize() == 1

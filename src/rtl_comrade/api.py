"""Core runtime message and contract-facing API types.

Edges between nodes carry exactly two runtime message types:

- Payload: wraps application data moving across an edge
- EndSentinel: marks that an upstream stream has ended
"""

from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar('T')

@dataclass(frozen=True, slots=True)
class Payload(Generic[T]):
	"""One of the two permitted runtime message types that may travel across an edge.

	Attributes:
		source: The upstream node id that emitted this payload.
		n: The per-destination sequence number assigned by the emitting node.
		payload: The wrapped value delivered to the downstream module input.
	"""

	source: str
	n: int
	payload: T

@dataclass(frozen=True, slots=True)
class EndSentinel:
	"""The other permitted runtime message type that may travel across an edge.

	Attributes:
		source: The upstream node id whose stream has ended.
	"""

	source: str

@dataclass(slots=True)
class ContractPort(Generic[T]):
	"""A contract-facing adapter around one node input port.

	Attributes:
		name: The input-port name as seen by the module and contract.
		get: Async blocking read for the next queued Payload or EndSentinel.
		try_get: Non-blocking read that returns a queued Payload, EndSentinel, or None.
		has_ended: Callable that reports whether this port has already observed an EndSentinel.
		has_default: Whether the corresponding module input has a Python default value.
		state: Contract-owned mutable state associated with this port.
	"""

	name: str
	get: Callable[[], Awaitable[Payload[T]|EndSentinel]]
	try_get: Callable[[], Payload[T]|EndSentinel|None]
	has_ended: Callable[[], bool]
	has_default: bool = False
	state: dict[str, Any] = field(default_factory=dict)

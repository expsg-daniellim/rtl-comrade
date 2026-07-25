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

@dataclass(frozen=True, slots=True)
class RestSentinel:
	"""Marker used as an ``output_groups`` member list meaning "all outputs not named in another group"."""

REST = RestSentinel()

@dataclass(slots=True)
class ContractPort(Generic[T]):  # pylint: disable=too-many-instance-attributes
	"""A contract-facing adapter around one node input port.

	A node's input and output contracts share one adapter per port, and so share its ``state``. Reads are only legal
	for the duration of a ``get_inputs()`` call: ``get`` and ``try_get`` raise IllegalGetAccessError anywhere else,
	including from ``process_outputs``.

	Attributes:
		name: The input-port name as seen by the module and contract.
		get: Async blocking read for the next queued Payload or EndSentinel.
		try_get: Non-blocking read that returns a queued Payload, EndSentinel, or None.
		has_ended: Callable that reports whether this port has already observed an EndSentinel.
		has_default: Whether the corresponding module input has a Python default value.
		required: Whether the graph config marks this port required; the default contract
			awaits a real value and ignores has_default for this port.
		branch_labels: Control-dependence labels — the branch arms whose non-selection can
			end this port's stream. Two ports are co-fated iff their label sets are equal.
		state: Contract-owned mutable state associated with this port.
	"""

	name: str
	get: Callable[[], Awaitable[Payload[T]|EndSentinel]]
	try_get: Callable[[], Payload[T]|EndSentinel|None]
	has_ended: Callable[[], bool]
	has_default: bool = False
	required: bool = False
	branch_labels: frozenset = field(default_factory=frozenset)
	state: dict[str, Any] = field(default_factory=dict)

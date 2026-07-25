"""Queue-backed input ports used by runtime nodes and contracts."""

from __future__ import annotations # Obsolete after 3.14
import asyncio
from asyncio import Queue
from dataclasses import dataclass, field
from typing import Generic, Self, TypeVar

from .api import Payload, EndSentinel
from .structure import ModuleStructureArg

T = TypeVar('T')

# Error when an item in the queue is not a Payload or EndSentinel.
@dataclass(slots=True)
class InvalidEnqueuedError(Exception):
	"""Raised when a port queue contains an unsupported runtime message type.

	Attributes:
		name: The affected port name.
		type_: The unexpected type name encountered in the queue.
	"""

	name: str
	type_: str

# Error when a port is read outside the get_inputs() call it is enabled for.
@dataclass(slots=True)
class IllegalGetAccessError(Exception):
	"""Raised when a port is read while its reads are disabled.

	Attributes:
		name: The affected port name.
		type_: The read that was attempted, ``"get"`` or ``"try_get"``.
	"""

	name: str
	type_: str

@dataclass(slots=True)
class Port(Generic[T]):
	"""One queue-backed runtime input port owned by a node.

	Attributes:
		name: Canonical external input-port name.
		param: The module ``run(...)`` parameter this port feeds; defaults to ``name`` for edge-built and contract-surface ports.
		queue: Async queue carrying Payload and EndSentinel messages.
		has_default: Whether the corresponding module input has a default value.
		ended: Whether this port has already observed an EndSentinel.
		get_enabled: Whether reads are currently permitted. The Node sets this only for the duration of a ``get_inputs()`` call, so an output contract — or an input contract holding onto a port past its call — cannot consume from the queue.
	"""

	name: str
	param: str = ''
	queue: Queue[Payload[T]|EndSentinel] = field(default_factory=Queue)
	has_default: bool = False
	ended: bool = False
	get_enabled: bool = False

	def __post_init__(self):
		if self.param == '':
			self.param = self.name

	@classmethod
	def from_structure(cls, arg:ModuleStructureArg) -> Self:
		"""Construct a Port from one inferred module input argument.

		Args:
			arg: Inferred module input argument metadata.

		Returns:
			A Port initialized from that argument description.
		"""

		return cls(name=arg.name, param=arg.param, has_default=arg.has_default)

	async def get(self) -> Payload[T]|EndSentinel:
		"""Wait for and return the next runtime message for this port.

		Returns:
			The next Payload or EndSentinel queued for this port.

		Raises:
			IllegalGetAccessError: Reads are not currently enabled on this port.
			InvalidEnqueuedError: The dequeued item is neither a Payload nor an EndSentinel.
		"""

		if not self.get_enabled:
			raise IllegalGetAccessError(self.name, 'get')

		val = await self.queue.get()
		if not isinstance(val, (Payload, EndSentinel)):
			raise InvalidEnqueuedError(self.name, type(val).__name__)

		if isinstance(val, EndSentinel):
			self.ended = True

		return val

	def try_get(self) -> Payload[T]|EndSentinel|None:
		"""Attempt a non-blocking read of the next runtime message for this port.

		Returns:
			The next queued Payload or EndSentinel, or ``None`` if the queue is empty.

		Raises:
			IllegalGetAccessError: Reads are not currently enabled on this port.
			InvalidEnqueuedError: The dequeued item is neither a Payload nor an EndSentinel.
		"""

		if not self.get_enabled:
			raise IllegalGetAccessError(self.name, 'try_get')

		val = None
		try:
			if not self.ended:
				val = self.queue.get_nowait()

				if isinstance(val, EndSentinel):
					self.ended = True
		except asyncio.QueueEmpty: # An empty queue is a valid case
			pass

		if not (isinstance(val, (Payload, EndSentinel)) or val is None):
			raise InvalidEnqueuedError(self.name, type(val).__name__)

		return val

	def has_ended(self) -> bool:
		"""Return whether this port has already seen an EndSentinel.

		Returns:
			``True`` if this port has ended, otherwise ``False``.
		"""

		return self.ended

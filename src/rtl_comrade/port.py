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
@dataclass(frozen=True, slots=True)
class InvalidEnqueuedError(Exception):
	"""Raised when a port queue contains an unsupported runtime message type.

	Attributes:
		name: The affected port name.
		type_: The unexpected type name encountered in the queue.
	"""

	name: str
	type_: str

@dataclass(slots=True)
class Port(Generic[T]):
	"""One queue-backed runtime input port owned by a node.

	Attributes:
		name: Canonical input-port name.
		queue: Async queue carrying Payload and EndSentinel messages.
		has_default: Whether the corresponding module input has a default value.
		ended: Whether this port has already observed an EndSentinel.
	"""

	name: str
	queue: Queue[Payload[T]|EndSentinel] = field(default_factory=Queue)
	has_default: bool = False
	ended: bool = False

	@classmethod
	def from_structure(cls, arg:ModuleStructureArg) -> Self:
		"""Construct a Port from one inferred module input argument.

		Args:
			arg: Inferred module input argument metadata.

		Returns:
			A Port initialized from that argument description.
		"""

		return cls(name=arg.name, has_default=arg.has_default)

	async def get(self) -> Payload[T]|EndSentinel:
		"""Wait for and return the next runtime message for this port.

		Returns:
			The next Payload or EndSentinel queued for this port.
		"""

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
		"""

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

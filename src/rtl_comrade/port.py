from __future__ import annotations # Obsolete after 3.14
import asyncio
from asyncio import Queue
from dataclasses import dataclass, field
from typing import Generic, TypeVar

from .api import Payload, EndSentinel
from .structure import ModuleStructureArg

T = TypeVar('T')

# Error when item in queue is not a Payload or EndSentinel
@dataclass(frozen=True, slots=True)
class InvalidEnqueuedError(Exception):
	name: str
	type_ : str

@dataclass
class Port(Generic[T]):
	name: str
	queue: Queue[Payload[T]|EndSentinel] = field(default_factory=Queue)
	has_default: bool = False
	default: T | None = None
	ended: bool = False

	@staticmethod
	def from_structure(arg:ModuleStructureArg) -> Port:
		return Port(name=arg.name, has_default=arg.has_default, default=arg.default)

	async def get(self) -> Payload[T]|EndSentinel:
		val =  await self.queue.get()
		if not (isinstance(val, Payload) or isinstance(val, EndSentinel)):
			raise InvalidEnqueuedError(self.name, type(val).__name__)

		if isinstance(val, EndSentinel):
			self.ended = True

		return val

	def try_get(self) -> Payload[T]|EndSentinel|None:
		val = None
		try:
			if not self.ended:
				val = self.queue.get_nowait()

				if isinstance(val, EndSentinel):
					self.ended = True
		except asyncio.QueueEmpty: # An empty queue is a valid case
			pass

		if not (isinstance(val, Payload) or isinstance(val, EndSentinel) or val is None):
			raise InvalidEnqueuedError(self.name, type(val).__name__)

		return val

	def has_ended(self) -> bool:
		return self.ended

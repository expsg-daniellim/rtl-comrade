from __future__ import annotations # Obsolete after 3.14
import asyncio
from asyncio import Queue
from dataclasses import dataclass
from inspect import Parameter
import typing

from .api import Payload, EndSentinel
from .structure import ModuleStructureArg

class PortError(Exception):
	def __init__(self, id, message):
		super().__init__(self, message)
		self.message = message
		self.id = id

	def __str__(self):
		return f"{self.id}: {self.message}"

# TODO: clean up typing with generics
@dataclass
class Port:
	name: str
	queue: Queue[Payload|EndSentinel] # a default Queue created here will be shared by every child
	has_default: bool = False
	default: typing.Any = None
	ended: bool = False

	@staticmethod
	def from_structure(arg:ModuleStructureArg) -> Port:
		return Port(name=arg.name, queue=Queue(), has_default=arg.has_default, default=arg.default)

	async def get(self) -> Payload|EndSentinel:
		val =  await self.queue.get()
		if not (isinstance(val, Payload) or isinstance(val, EndSentinel)):
			raise PortError(self.name, f"invalid enqueued type {type(val).__name__}")

		if isinstance(val, EndSentinel):
			self.ended = True

		return val

	def try_get(self) -> Payload|EndSentinel|None:
		val = None
		try:
			if not self.ended:
				val = self.queue.get_nowait()

				if isinstance(val, EndSentinel):
					self.ended = True
		except asyncio.QueueEmpty:
			pass

		if not (isinstance(val, Payload) or isinstance(val, EndSentinel) or val is None):
			raise PortError(self.name, f"invalid enqueued type {type(val).__name__}")
		return val

	def has_ended(self) -> bool:
		return self.ended

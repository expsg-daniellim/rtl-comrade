from collections.abc import Callable, Awaitable
from dataclasses import dataclass, field
from typing import Generic, TypeVar

T = TypeVar('T')

# Edges between nodes can hold one of two data types - a Payload wrapping the actual data or an EndSentinel
@dataclass(frozen=True, slots=True)
class Payload(Generic[T]):
	source: str
	n: int
	payload: T

@dataclass(frozen=True, slots=True)
class EndSentinel:
	source: str

@dataclass
class NoDefaultError(Exception):
	name: str

# ContractPort holds the data relating to one port for the use of the contract
# ContractPort is not a frozen dataclass so contracts can use it to carry their own mutable state
@dataclass
class ContractPort(Generic[T]):
	name: str
	get: Callable[[], Awaitable[Payload[T]|EndSentinel]]
	try_get: Callable[[], Payload[T]|EndSentinel|None]
	has_ended: Callable[[], bool]
	has_default: bool = False
	default: T | None = None
	default_n: int = 0

	def get_default_payload(self) -> Payload[T]:
		if not self.has_default:
			raise NoDefaultError(self.name)

		payload = Payload("_default", self.default_n, self.default)
		self.default_n += 1
		return payload

from collections.abc import Callable, Awaitable
from dataclasses import dataclass
import typing

# TODO: clean up typing with generics
@dataclass(frozen=True, slots=True)
class Payload:
	source: str
	n: int
	payload: typing.Any

@dataclass(frozen=True, slots=True)
class EndSentinel:
	source: str

# ContractPort is not a frozen dataclass so contracts can use it to carry their own mutable state
@dataclass
class ContractPort:
	get: Callable[[], Awaitable[Payload|EndSentinel]]
	try_get: Callable[[], Payload|EndSentinel|None]
	has_ended: Callable[[], bool]
	has_default: bool = False
	default: typing.Any = None
	default_n: int = 0

	def get_default_payload(self) -> Payload:
		if not self.has_default:
			raise AttributeError("no default available")

		payload = Payload("_default", self.default_n, self.default)
		self.default_n += 1
		return payload

"""Payload types owned by the contract layer: stream-control sentinels and the keyed-value wrapper."""

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class GroupEnd:
	"""Signals the end of one group within a port stream.

	Emit this as a payload value to close the current group and allow the
	GroupUntilEndContract to begin accumulating the next group. Multiple groups
	per stream are possible; the stream itself ends when EndSentinel arrives.
	"""


@dataclass(frozen=True)
class KeyedValue(Generic[T]):
	"""A value tagged with a correlation key so KeyedJoinContract can match it across ports.

	Attributes:
		key: The correlation key.
		value: The wrapped value.
	"""

	key:str
	value:T

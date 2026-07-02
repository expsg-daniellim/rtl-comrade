"""Sentinel values for contract-level stream control signals."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GroupEnd:
	"""Signals the end of one group within a port stream.

	Emit this as a payload value to close the current group and allow the
	GroupUntilEndContract to begin accumulating the next group. Multiple groups
	per stream are possible; the stream itself ends when EndSentinel arrives.
	"""

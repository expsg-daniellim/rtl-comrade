"""Sentinel values for contract-level stream control signals."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GroupEnd:
    """Signals the end of one group within a port stream.

    Emit this as a payload value to close the current group and allow the
    GroupUntilEndContract to begin accumulating the next group. Multiple groups
    per stream are possible; the stream itself ends when EndSentinel arrives.
    """


@dataclass(frozen=True)
class BranchSkip:
    """Signals that a control-flow branch was intentionally not taken for a given key.

    Emit this as a payload value on a port that was bypassed by an if/else routing
    node. BranchAwareJoinContract treats a port carrying BranchSkip(key=k) as
    satisfied for key k and excludes it from the module invocation.
    """

    key: Any

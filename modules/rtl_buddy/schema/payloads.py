from dataclasses import dataclass
from pathlib import Path

# KeyedValue is owned by the contract layer: keyed_join both reads and constructs it.
from contracts.sentinels import KeyedValue  # noqa: F401  # pylint: disable=unused-import


@dataclass(frozen=True)
class Command:
	key:str
	argv:list[str]
	stdout_path:Path
	stderr_path:Path


@dataclass(frozen=True)
class Proc:
	key:str
	rc:int | None
	stdout_path:Path
	stderr_path:Path


@dataclass(frozen=True)
class RandSeed:
	key:str
	seed:int
	randseed_path:Path
	argv:list[str]


@dataclass(frozen=True)
class RandSeedDone:
	key:str

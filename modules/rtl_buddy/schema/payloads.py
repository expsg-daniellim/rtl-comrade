from dataclasses import dataclass
from pathlib import Path
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class KeyedValue(Generic[T]):
    key:str
    value:T


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

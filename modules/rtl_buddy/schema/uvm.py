from dataclasses import dataclass

from serde import serde, field


@serde
@dataclass
class UVMConfig:
    """Per-test UVM report parsing configuration."""

    max_warns:int = field(default=0)
    max_errors:int = field(default=0)

    def __post_init__(self):
        if self.max_warns < 0:
            raise ValueError
        if self.max_errors < 0:
            raise ValueError

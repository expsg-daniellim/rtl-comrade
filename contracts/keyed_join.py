from dataclasses import dataclass, field
from typing import Any

from rtl_comrade.api import Payload, EndSentinel, ContractPort
import structlog

log = structlog.get_logger()


@dataclass
class KeyedJoinContract:
    """Invokes the module when all required ports have data for the same correlation key.

    Items from different ports are matched by a field in their payload dict (``key_field``).
    Keys may arrive interleaved across ports; partial groups are buffered until complete.
    When any port ends with buffered incomplete keys, those keys are logged as an error.
    """

    @dataclass(frozen=True)
    class Config:
        key_field: str

    id: str
    ports: dict[str, ContractPort]
    config: Config
    _buffers: dict[str, dict[Any, Payload]] = field(default_factory=dict, init=False, repr=False)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        saw_end: list[str] = []

        while True:
            for name, port in self.ports.items():
                if port.has_ended():
                    continue
                while True:
                    val = port.try_get()
                    if val is None:
                        break
                    if isinstance(val, EndSentinel):
                        saw_end.append(name)
                        break
                    key = val.payload[self.config.key_field]
                    self._buffers.setdefault(name, {})[key] = val

            complete_key = self._find_complete_key()
            if complete_key is not None:
                return {name: self._buffers[name].pop(complete_key) for name in self.ports}

            if saw_end:
                incomplete = self._find_incomplete_keys()
                if incomplete:
                    log.error('incomplete_keys', contract=self.id, keys=incomplete)
                return EndSentinel(self.id)

            if all(port.has_ended() for port in self.ports.values()):
                return EndSentinel(self.id)

            for name, port in self.ports.items():
                if not port.has_ended():
                    val = await port.get()
                    if isinstance(val, EndSentinel):
                        saw_end.append(name)
                    else:
                        key = val.payload[self.config.key_field]
                        self._buffers.setdefault(name, {})[key] = val
                    break

    def _find_complete_key(self) -> Any:
        all_keys: set[Any] = set()
        for name in self.ports:
            all_keys |= set(self._buffers.get(name, {}).keys())
        complete = [k for k in all_keys if all(k in self._buffers.get(n, {}) for n in self.ports)]
        return min(complete) if complete else None

    def _find_incomplete_keys(self) -> list[Any]:
        all_keys: set[Any] = set()
        for name in self.ports:
            all_keys |= set(self._buffers.get(name, {}).keys())
        return [k for k in all_keys if not all(k in self._buffers.get(n, {}) for n in self.ports)]

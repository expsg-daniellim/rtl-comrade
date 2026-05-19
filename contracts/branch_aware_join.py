from dataclasses import dataclass, field
from typing import Any

from rtl_comrade.api import Payload, EndSentinel, ContractPort

from contracts.sentinels import BranchSkip


@dataclass
class BranchAwareJoinContract:
    """Joins inputs by key while tolerating intentionally skipped branches.

    A port carrying ``BranchSkip(key=k)`` is treated as satisfied for key ``k``
    and excluded from the returned dict. The module must declare default values
    for any port that may be absent from the result.
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
                    key = val.payload.key if isinstance(val.payload, BranchSkip) else val.payload[self.config.key_field]
                    self._buffers.setdefault(name, {})[key] = val

            complete_key = self._find_complete_key()
            if complete_key is not None:
                result = {}
                for name in self.ports:
                    payload = self._buffers[name].pop(complete_key)
                    if not isinstance(payload.payload, BranchSkip):
                        result[name] = payload
                return result

            if saw_end:
                return EndSentinel(self.id)

            if all(port.has_ended() for port in self.ports.values()):
                return EndSentinel(self.id)

            for name, port in self.ports.items():
                if not port.has_ended():
                    val = await port.get()
                    if isinstance(val, EndSentinel):
                        saw_end.append(name)
                    else:
                        key = val.payload.key if isinstance(val.payload, BranchSkip) else val.payload[self.config.key_field]
                        self._buffers.setdefault(name, {})[key] = val
                    break

    def _find_complete_key(self) -> Any:
        all_keys: set[Any] = set()
        for name in self.ports:
            all_keys |= set(self._buffers.get(name, {}).keys())
        complete = [k for k in all_keys if all(k in self._buffers.get(n, {}) for n in self.ports)]
        return min(complete) if complete else None

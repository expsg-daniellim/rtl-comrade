from dataclasses import dataclass, field
from typing import Any

from rtl_comrade.api import Payload, EndSentinel, ContractPort
import structlog

log = structlog.get_logger()


@dataclass
class LatestContract:
    """Invokes the module on each trigger input using the most-recent state values.

    State ports are read eagerly and cached; their latest value is reused across
    invocations. Trigger ports drive the invocation cadence: one invocation per
    trigger item. The stream ends when any trigger port ends.
    """

    @dataclass(frozen=True)
    class Config:
        trigger_ports: list[str]

    id: str
    ports: dict[str, ContractPort]
    config: Config
    _latest: dict[str, Payload] = field(default_factory=dict, init=False, repr=False)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        trigger_names = set(self.config.trigger_ports)
        state_names = [n for n in self.ports if n not in trigger_names]

        for name in state_names:
            if name not in self._latest:
                val = await self.ports[name].get()
                if isinstance(val, EndSentinel):
                    return EndSentinel(self.id)
                self._latest[name] = val

        for name in state_names:
            while not self.ports[name].has_ended():
                val = self.ports[name].try_get()
                if val is None:
                    break
                if isinstance(val, EndSentinel):
                    break
                self._latest[name] = val

        for name in self.ports:
            if name not in trigger_names:
                continue
            if not self.ports[name].has_ended():
                val = await self.ports[name].get()
                if isinstance(val, EndSentinel):
                    return EndSentinel(self.id)
                return {**self._latest, name: val}

        return EndSentinel(self.id)

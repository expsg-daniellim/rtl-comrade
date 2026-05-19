from dataclasses import dataclass

from rtl_comrade.api import Payload, EndSentinel, ContractPort

from contracts.sentinels import GroupEnd


@dataclass
class GroupUntilEndContract:
    """Accumulates port items into per-port lists until each port emits a GroupEnd payload.

    Each call to ``get_inputs`` collects one group per port. The module is invoked once
    with a dict mapping each port name to a Payload whose ``.payload`` is the list of
    raw values received before GroupEnd. Multiple groups per stream are supported by
    calling ``get_inputs`` repeatedly. The stream ends when any port emits EndSentinel.
    """

    id: str
    ports: dict[str, ContractPort]

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        buffers: dict[str, list] = {name: [] for name in self.ports}
        done: dict[str, bool] = {name: False for name in self.ports}

        while not all(done.values()):
            for name, port in self.ports.items():
                if done[name]:
                    continue
                val = await port.get()
                if isinstance(val, EndSentinel):
                    return EndSentinel(self.id)
                if isinstance(val.payload, GroupEnd):
                    done[name] = True
                else:
                    buffers[name].append(val.payload)

        return {name: Payload(source=self.id, n=0, payload=buffers[name]) for name in self.ports}

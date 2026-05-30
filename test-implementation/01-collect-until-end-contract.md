# Spec 01: FanInContract

## What this covers

Implement `FanInContract` in `contracts/fan_in.py` and register it in `contracts/config.yaml`. This contract powers `SuiteResultAccumulate` — it multiplexes N named input ports into a single streaming interface, delivering one item at a time to `module.run()`.

## Before you start

Read:
- `docs/contract-implementation.md` — required interface (`get_inputs()`, `ports`, `EndSentinel`)
- `contracts/group_until_end.py` — the closest existing contract; understand how it works before writing this one
- `contracts/config.yaml` — how to register a new contract

## Key behavioral difference from `GroupUntilEndContract`

`GroupUntilEndContract` accumulates items into a list and fires `run()` once per group. That is wrong for this use case.

`FanInContract` must:
1. Wait for any non-ended port to deliver an item.
2. Deliver that single item to `module.run()` immediately via a synthetic `"item"` port.
3. When a port delivers `EndSentinel`, mark it done and stop reading from it.
4. When **all** ports have delivered `EndSentinel`: return `EndSentinel` on the next `get_inputs()` call.

The module is responsible for accumulation across invocations (via instance state). The contract is responsible only for delivery and termination detection.

## File: `contracts/fan_in.py`

```python
from dataclasses import dataclass, field
from rtl_comrade.api import Payload, EndSentinel, ContractPort


@dataclass
class FanInContract:
    id: str
    ports: dict[str, ContractPort]
    _ended: set = field(default_factory=set, init=False)

    async def get_inputs(self) -> dict[str, Payload] | EndSentinel:
        while len(self._ended) < len(self.ports):
            for name, port in self.ports.items():
                if name in self._ended:
                    continue
                val = await port.get()
                if isinstance(val, EndSentinel):
                    self._ended.add(name)
                else:
                    return {"item": Payload(source=self.id, n=0, payload=val.payload)}
        return EndSentinel(self.id)
```

**Note on the inner loop**: the round-robin `for` iterates ports in declaration order, blocking on `await port.get()` for each non-ended port. When a real item arrives it is returned immediately; when `EndSentinel` arrives the port is retired and the loop continues. For the test graph this is correct — volume is small (dozens of result rows at most) and order of delivery to `run()` is irrelevant since the module sorts on `finalise()`.

## Register in `contracts/config.yaml`

Append to the `files` list:

```yaml
- file: fan_in.py
  plugins:
  - name: fan_in
    class_name: FanInContract
```

## Tests

Write `contracts/tests/test_fan_in.py`.

Look at `contracts/tests/test_group_until_end.py` and `contracts/tests/conftest.py` for patterns.

Scenarios to cover:

1. **Two ports, interleaved items**: port A delivers 2 items then `EndSentinel`; port B delivers 1 item then `EndSentinel`. Verify `get_inputs()` is called 3 times and returns an `{"item": ...}` dict each time. Verify the 4th call returns `EndSentinel`.

2. **One port delivers nothing**: port A delivers 2 items then ends; port B delivers `EndSentinel` immediately. Verify only 2 item deliveries occur before `EndSentinel`.

3. **Single port**: one port delivers 3 items then ends. Verify 3 item deliveries then `EndSentinel`.

4. **Ports end at different times**: port A ends first; verify the contract keeps reading from port B until it also ends.

## Constraints

- Do not modify `GroupUntilEndContract`.
- The contract must deliver items one at a time — never accumulate.
- The `"item"` key in the returned dict is the synthetic port name; `module.run()` must accept a parameter named `item`.
- `EndSentinel` is returned only after all ports are exhausted.

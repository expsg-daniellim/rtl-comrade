# `any`

**Class:** `AnyContract` (`contracts/any.py`)

[Back to index](index.md)

Fires on whichever input port delivers a value first, one value per `get_inputs()` call. Ends once every port has ended. General-purpose fan-in — reusable across any graph that needs to collect items from multiple upstream ports into a single downstream node without a fixed ordering or zipping constraint.

General-purpose fan-in — reusable across any graph that needs to collect items from multiple upstream ports into a single downstream node without a fixed ordering or zipping constraint.

## Invariants

- **One delivery per call.** Each `get_inputs()` returns exactly one `{output_port: payload}` dict. If multiple ports are simultaneously ready, only one is consumed; the others remain pending for the next call.
- **No-loss.** A task created for a port that was not returned in the current call is never cancelled; its value is returned on a subsequent call.
- **Silent `EndSentinel` consumption.** When a port's task returns `EndSentinel`, that sentinel is consumed and the scan continues to the next ready port. The contract's own `EndSentinel` is returned only after every port has ended and `pending` is empty.
- **Output resolved once at construction.** Each port's output name is stored in `port.state['output']` during `__post_init__` and read back on every delivery. The `str` branch sets the same name for all ports (n→1); the `dict` branch assigns each input port its group's output name (m→n).

## Config

```yaml
contract:
  name: any
  config:
    mapping: results
```

| Field | Type | Purpose |
|---|---|---|
| `mapping` | `str` \| `dict[str, list[str]]` | n→1: a single output port name that every input funnels onto (default `"default"`). m→n: a map of output port name → list of input port names; every input port must appear in exactly one group |

The config may be omitted entirely (bare `contract: any`); the contract then behaves as n→1 onto `"default"`.

### m→n example

```yaml
contract:
  name: any
  config:
    mapping:
      fast: [stage_a, stage_b]
      slow: [stage_c]
```

Inputs `stage_a` and `stage_b` funnel onto output port `fast`; `stage_c` funnels onto `slow`. Every input port must appear in exactly one group — an unknown port, a port claimed by two groups, or a real port left out of all groups is a construction-time fatal.

## Termination

Ends when all input ports have ended and no pending tasks remain. Partial endings (some ports ended, others still live) are handled silently: the contract keeps delivering from the remaining live ports.

## Example use cases

**Merging parallel streams into one.** Two enrichment pipelines produce records at different rates. A downstream aggregator uses `any` (n→1 onto `"default"`) to receive whichever record arrives first, processing each immediately rather than waiting for both.

# `port.py`

Source: [src/rtl_comrade/port.py](../../src/rtl_comrade/port.py)

## Role

This file implements the queue-backed input ports owned by each runtime node.

## See Also

- [README.md](README.md)
- [node.md](node.md)
- [api.md](api.md)
- [contract.md](contract.md)
- [contract_default.md](contract_default.md)

## Main Responsibilities

- hold inbound `Payload` and `EndSentinel` objects
- expose blocking and non-blocking reads, gated by the node's read window (`get_enabled`)
- track whether every source feeding the port has ended (`source_n`, `ends_seen`)
- record whether the corresponding module parameter has a Python default (`has_default`)
- carry the module `run(...)` parameter name (`param`) the port feeds, defaulting to `name` for edge-built and contract-surface ports

## Place In The System

`Port` is the concrete runtime transport primitive behind the higher-level `ContractPort` API.

## Key Behaviors

- `Port.from_structure(...)` builds a port from `ModuleStructureArg`, carrying both its external `name` and its `param`
- `node.py` re-keys inbound payloads from external port `name` to `param` immediately before `run(**inputs)`, so the module receives its literal parameter names
- `get()` awaits the next queued item
- `try_get()` performs a non-blocking queue read
- `source_n` is the port's incoming edge count, set from the wired graph and defaulting to 1; each of those edges sends its own `EndSentinel`
- reading an `EndSentinel` marks the port as ended only once one has arrived from every source. Both reads swallow the earlier ones — `get()` keeps awaiting, `try_get()` keeps draining and reports `None` if nothing else is there — so a port whose other sources are still live neither ends nor reports a false quiet
- unexpected enqueued object types raise `InvalidEnqueuedError`
- reading while `get_enabled` is `False` raises `IllegalGetAccessError`, before the queue is touched

## The Read Window

`get_enabled` is the port's own half of a node-level invariant: a port is readable only for the duration of a `get_inputs()` call. `Node.run` sets the flag on every port immediately before invoking the input contract and clears it immediately after, so the flag is `False` at every other point in the node's lifetime — during module execution, during the output contract's `process_outputs`, and after the node stops.

Both reads check the flag first and raise `IllegalGetAccessError(name, 'get' | 'try_get')` without consuming anything, so a rejected read leaves the queue untouched. `node.py` treats the error as fatal.

The flag defaults to `False`, so a `Port` constructed outside `Node.run` — in a test, say — rejects reads until something enables it. `rtl_comrade.testing.run_contract_scenario` reproduces the window rather than leaving ports open; see [../contracts/testing.md](../contracts/testing.md).

## Caveats

- ports do not implement scheduling policy themselves; contracts decide how ports are consumed
- `try_get()` treats an empty queue as a normal condition, not an error
- `get_enabled` is transport-level state on the shared `Port`, not on the per-contract `ContractPort` adapter, so opening the window opens it for every contract on the node at once; the window is a lifetime guarantee, not a per-contract permission

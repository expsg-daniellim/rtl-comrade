# `port.py`

Source: [src/rtl_comrade/port.py](../../src/rtl_comrade/port.py)

## Role

This file implements the queue-backed input ports owned by each runtime node.

## See Also

- [README.md](README.md)
- [node.md](node.md)
- [api.md](api.md)
- [contract_default.md](contract_default.md)

## Main Responsibilities

- hold inbound `Payload` and `EndSentinel` objects
- expose blocking and non-blocking reads
- track whether a port has ended
- record whether the corresponding module parameter has a Python default (`has_default`)
- carry the module `run(...)` parameter name (`param`) the port feeds, defaulting to `name` for edge-built and contract-surface ports

## Place In The System

`Port` is the concrete runtime transport primitive behind the higher-level `ContractPort` API.

## Key Behaviors

- `Port.from_structure(...)` builds a port from `ModuleStructureArg`, carrying both its external `name` and its `param`
- `node.py` re-keys inbound payloads from external port `name` to `param` immediately before `run(**inputs)`, so the module receives its literal parameter names
- `get()` awaits the next queued item
- `try_get()` performs a non-blocking queue read
- reading an `EndSentinel` marks the port as ended
- unexpected enqueued object types raise `InvalidEnqueuedError`

## Caveats

- ports do not implement scheduling policy themselves; contracts decide how ports are consumed
- `try_get()` treats an empty queue as a normal condition, not an error

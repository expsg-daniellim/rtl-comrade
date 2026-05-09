# `port.py`

Source: [src/rtl_comrade/port.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/port.py)

## Role

This file implements the queue-backed input ports owned by each runtime node.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md)
- [contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md)

## Main Responsibilities

- hold inbound `Payload` and `EndSentinel` objects
- expose blocking and non-blocking reads
- track whether a port has ended
- capture default metadata inferred from module signatures

## Place In The System

`Port` is the concrete runtime transport primitive behind the higher-level `ContractPort` API.

## Key Behaviors

- `Port.from_structure(...)` builds a port from `ModuleStructureArg`
- `get()` awaits the next queued item
- `try_get()` performs a non-blocking queue read
- reading an `EndSentinel` marks the port as ended
- unexpected enqueued object types raise `InvalidEnqueuedError`

## Caveats

- ports do not implement scheduling policy themselves; contracts decide how ports are consumed
- `try_get()` treats an empty queue as a normal condition, not an error

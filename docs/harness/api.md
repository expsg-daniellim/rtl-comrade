# `api.py`

Source: [src/rtl_comrade/api.py](../../src/rtl_comrade/api.py)

## Role

This file defines the small set of core data types shared across the harness and contracts.

## See Also

- [README.md](README.md)
- [node.md](node.md)
- [port.md](port.md)
- [contract.md](contract.md)
- [contract_default.md](contract_default.md)

## Main Types

- `Payload[T]`: wraps a value moving across an edge
- `EndSentinel`: marks stream termination
- `ContractPort[T]`: contract-facing access wrapper around a node input port

## Place In The System

This is the harness boundary API for data movement and contract interaction. `node.py`, `port.py`, `contract_default.py`, and custom contracts all depend on these types.

## Important Details

- `Payload` records `source`, `n`, and `payload`
- `ContractPort` exposes both blocking `get()` and non-blocking `try_get()`
- both reads are legal only for the duration of a `get_inputs()` call; anywhere else — including from an output contract's `process_outputs` — they raise `IllegalGetAccessError`. See [port.md](port.md)
- `ContractPort.state` is the intended place for contract-owned per-port mutable state
- a node builds one `ContractPort` per input port and hands the same mapping to every contract it has, so a node's input and output contracts share these objects and their `state`

## Caveats

- contracts can and do use `ContractPort.state`, so these objects are part API surface and part scheduling state carrier
- `state` is shared across a node's contracts, so two contracts using the same key on the same port will clobber each other; that sharing is the intended channel between an input and an output contract
- `ContractPort` is handed to output contracts that ask for `ports` even though they cannot read from them — the adapter is useful there for `name`, `has_ended()`, `branch_labels`, and `state`
- the exact meaning of `Payload.n` is currently "per-destination dispatch count", not a global sequence number

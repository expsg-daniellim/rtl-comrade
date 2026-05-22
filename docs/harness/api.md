# `api.py`

Source: [src/rtl_comrade/api.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/api.py)

## Role

This file defines the small set of core data types shared across the harness and contracts.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [port.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/port.md)
- [contract_default.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/contract_default.md)

## Main Types

- `Payload[T]`: wraps a value moving across an edge
- `EndSentinel`: marks stream termination
- `ContractPort[T]`: contract-facing access wrapper around a node input port

## Place In The System

This is the harness boundary API for data movement and contract interaction. `node.py`, `port.py`, `contract_default.py`, and custom contracts all depend on these types.

## Important Details

- `Payload` records `source`, `n`, and `payload`
- `ContractPort` exposes both blocking `get()` and non-blocking `try_get()`
- `ContractPort.state` is the intended place for contract-owned per-port mutable state

## Caveats

- contracts can and do use `ContractPort.state`, so these objects are part API surface and part scheduling state carrier
- the exact meaning of `Payload.n` is currently "per-destination dispatch count", not a global sequence number

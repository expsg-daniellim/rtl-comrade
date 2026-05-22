# `contract_default.py`

Source: [src/rtl_comrade/contract_default.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/contract_default.py)

## Role

This file provides the built-in default contract used when a node does not name a custom contract.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md)
- [port.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/port.md)
- [validation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/validation.md)

## Main Responsibilities

- classify ports as required or special
- wait for required inputs
- support default-valued inputs
- support `persistent_inputs` with cached last values
- terminate cleanly when required inputs end

## Place In The System

This is the harness’s baseline scheduling policy. It is not part of the generic node runtime, but it is the default policy most graphs will run under unless they opt into a custom contract.

## Behavior Summary

- non-default, non-cached inputs are required and awaited
- persistent inputs remember the last real payload they saw
- default-valued ports that have no queued payload are omitted from the returned dict; Python's own default argument activates when the module is called
- if any required port returns `EndSentinel`, the contract returns `EndSentinel` for the whole node
- port-local persistent state is stored in each `ContractPort.state` dict

## Caveats

- the static deadlock validator is only loosely aligned with contract-specific behavior
- this contract relies on `ContractPort.state` for persistent-input bookkeeping, so changes here affect scheduling semantics directly

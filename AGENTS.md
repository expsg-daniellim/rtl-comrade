# AGENTS.md

## Purpose

This repository contains a prototype of `rtl-comrade`: a graph runner that executes modular Python nodes under contract-driven scheduling.

The codebase has three distinct workstreams:

- harness work: improving the runtime framework in [src/rtl_comrade](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade)
- contract work: defining input-consumption and scheduling policy in [contracts](/Users/daniellim/Documents/random/rtl-comrade/contracts)
- module work: defining node-local behavior in [modules](/Users/daniellim/Documents/random/rtl-comrade/modules)

Use this file as a routing and invariants document. Use the code and linked docs as the detailed source of truth.

## Where To Read

### If you are changing the harness

Start with [docs/harness/README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md).

That folder contains the per-file harness documentation for:

- CLI entrypoint
- graph loading and assembly
- node instantiation and execution
- structure inference
- default contract behavior
- plugin loading
- config schema
- payload/port API types
- validation
- logging and failure semantics

### If you are writing or changing modules

Read the module conventions below, then inspect:

- [docs/module-implementation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/module-implementation.md)
- [modules/io.py](/Users/daniellim/Documents/random/rtl-comrade/modules/io.py)
- [modules/funcs.py](/Users/daniellim/Documents/random/rtl-comrade/modules/funcs.py)
- [modules/config.yaml](/Users/daniellim/Documents/random/rtl-comrade/modules/config.yaml)

### If you are writing or changing contracts

Read the contract conventions below, then inspect:

- [docs/contract-implementation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/contract-implementation.md)
- [contracts/contracts.py](/Users/daniellim/Documents/random/rtl-comrade/contracts/contracts.py)
- [contracts/config.yaml](/Users/daniellim/Documents/random/rtl-comrade/contracts/config.yaml)
- [contracts-to-implement.md](/Users/daniellim/Documents/random/rtl-comrade/contracts-to-implement.md)

## Repository Split

- [src/rtl_comrade](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade) is the harness.
- [modules](/Users/daniellim/Documents/random/rtl-comrade/modules) and [contracts](/Users/daniellim/Documents/random/rtl-comrade/contracts) are modular building blocks loaded by the harness.

Keep that split intact:

- harness code should own graph loading, validation, orchestration, ports, and failure semantics
- contracts should own scheduling and input-consumption policy
- modules should own node-local work, not graph scheduling

## Global Invariants

These matter across all three workstreams:

- `EndSentinel` behavior is core to the runtime. Changes here can deadlock graphs or stop them too early.
- Graph loading and validation are intentionally fail-fast. A malformed graph should be rejected before runtime.
- Runtime logging is intentionally part of the failure model:
  - `DEBUG` / `INFO` / `WARNING` behave normally
  - `ERROR` is deferred failure and allows best-effort completion before a failing exit
  - `CRITICAL` is immediate failure
- Static output-port inference in `structure.py` is intentionally conservative. Dynamic output names are allowed, but they weaken what validation can prove.
- Destination input ports take multiple upstream edges only as alternatives — the sources must be provably mutually-exclusive branch arms. Anything else is an overloaded input.

## Module Conventions

Modules are plain Python classes discovered from plugin files.

- A module must expose `run(...)`.
- `run(...)` parameters define input ports in declaration order.
- Default argument values on `run(...)` become default-valued input ports.
- If `__init__` accepts `config`, the node config is passed in.
- If the module defines `Config`, node config is deserialized before construction.
- If `__init__` accepts `id`, the harness passes `<node-id>.module`.
- `run(...)` may be sync, async, a generator, or an async generator.
- Returning `None` emits nothing.
- Returning a non-tuple non-`None` value emits on the `"default"` port.
- Returning or yielding `(port_name, value)` emits on a named port, and `port_name` must be a string.

## Contract Conventions

Contracts are plain Python classes that decide when a node should run.

- A contract must expose `get_inputs()`.
- `get_inputs()` may be sync or async.
- `get_inputs()` must return either `dict[str, Payload]` or `EndSentinel`.
- If `__init__` accepts `config`, `contract_config` is passed in.
- If the contract defines `Config`, `contract_config` is deserialized before construction.
- If `__init__` accepts `id`, the harness passes `<node-id>.contract`.
- If `__init__` accepts `ports`, the harness passes contract-facing port adapters.

In practice, useful contracts should accept `ports`.

## Config Shape

Graph YAML currently supports:

- `modules`: plugin paths
- `contracts`: contract plugin paths
- `nodes`: node definitions
- `edges`: graph connections

Current checked-in example:

- [graph2.yaml](/Users/daniellim/Documents/random/rtl-comrade/graph2.yaml)

## Contribution Guidance

- Keep changes local to the seam you are editing.
- Do not move scheduling policy into modules.
- If you change harness behavior that affects plugin authoring, update the corresponding docs in [docs/harness](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md).
- If you change config shape, port semantics, or plugin loading behavior, update the sample graph and manifests in the same change.
- Prefer executable examples when introducing runtime features; this repository still has no committed automated test suite.
- Do not assume [README.md](/Users/daniellim/Documents/random/rtl-comrade/README.md) is the authoritative architecture document.

## Current Project State

- The CLI in [src/rtl_comrade/__main__.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/__main__.py) is intentionally barebones and mainly for basic testing.
- The intended long-term CLI direction is `typer`, but that does not exist yet.
- The current CLI defaults to `graph.yaml`, but no such file is checked in.
- The repository still has no committed automated test suite.

## Practical Commands

Typical entrypoints:

```bash
uv run rtl-comrade graph2.yaml
uv run python -m rtl_comrade graph2.yaml
```

Package metadata:

- [pyproject.toml](/Users/daniellim/Documents/random/rtl-comrade/pyproject.toml)
- Python requirement: `>=3.11`
- Runtime dependencies: `pyserde[yaml]`, `structlog`

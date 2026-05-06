# AGENTS.md

## Purpose

This repository is an early implementation of `rtl-comrade`, a graph-based RTL workflow runner intended to generalize `rtl_buddy`.

The codebase already contains a minimal runnable graph engine, dynamic module/contract loading, and static validation, but it is still clearly in prototype stage.

## Repository Structure

- [src/rtl_comrade](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade): core package.
- [src/rtl_comrade/__main__.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/__main__.py): CLI entrypoint. Loads `graph.yaml` by default or a path from `argv[1]`.
- [src/rtl_comrade/graph.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/graph.py): builds a `Graph` from YAML config, loads plugin folders, wires edges, and runs all nodes concurrently.
- [src/rtl_comrade/module.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/module.py): wraps module classes, instantiates their analyzed structure, dispatches outputs, and propagates end sentinels.
- [src/rtl_comrade/structure.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/structure.py): inspects module `run(...)` signatures and ASTs to derive input arguments plus statically known emitted output ports.
- [src/rtl_comrade/contract.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/contract.py): wraps contract classes and normalizes access to `get_inputs()`.
- [src/rtl_comrade/contract_default.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/contract_default.py): default scheduling/input contract, including persistent-input support.
- [src/rtl_comrade/loader.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/loader.py): plugin/module discovery from folders and `config.yaml` manifests.
- [src/rtl_comrade/config.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/config.py): serde-backed graph config schema.
- [src/rtl_comrade/api.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/api.py): payload and contract-facing API types.
- [src/rtl_comrade/port.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/port.py): queue-backed port implementation.
- [src/rtl_comrade/validation.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/validation.py): acyclicity and static deadlock checks.
- [modules](/Users/daniellim/Documents/random/rtl-comrade/modules): example module plugins and manifest.
- [contracts](/Users/daniellim/Documents/random/rtl-comrade/contracts): example contract plugins and manifest.
- [graph2.yaml](/Users/daniellim/Documents/random/rtl-comrade/graph2.yaml): checked-in sample graph.
- [contracts-to-implement.md](/Users/daniellim/Documents/random/rtl-comrade/contracts-to-implement.md): design backlog for additional contract strategies.
- [README.md](/Users/daniellim/Documents/random/rtl-comrade/README.md): currently minimal and not the source of truth.

## Current Execution Model

The current runtime is small but coherent:

1. `rtl-comrade` starts in `__main__.py`.
2. `Graph.from_file()` deserializes YAML into `GraphConfig`.
3. `load_folders()` loads module and contract classes from configured folders.
4. Each graph node becomes a `ModuleWrapper`.
5. `ModuleStructure` inspects the module `run(...)` signature and return/yield AST to infer input ports and known output ports.
6. `ModuleWrapper` turns those inferred inputs into `Port` objects.
7. A `ContractWrapper` decides when enough inputs are ready to invoke that module.
8. Module outputs are pushed to downstream queues as `Payload` objects.
9. `EndSentinel` values propagate through downstream ports to terminate the graph.

This means the repository is already beyond “design only”, but still clearly in prototype stage.

## Plugin Conventions

### Modules

Module classes are normal Python classes discovered from plugin files.

- A module must expose a callable `run(...)`.
- `run(...)` parameters define input ports in declaration order.
- If `__init__` accepts `config`, the loader passes node config into it.
- If the class defines `Config`, it is deserialized via `serde.from_dict`.
- Output ports are analyzed from the `run(...)` AST. Static string port names in returned/yielded `(port_name, value)` tuples are tracked and used for graph validation.
- Outputs may be returned as:
  - a single value for the default output port
  - a `(port_name, value)` tuple
  - a generator / async generator yielding either of the above
- Returning `None` emits nothing. This is now treated as a no-op rather than as a default-port payload.

Examples live in [modules/io.py](/Users/daniellim/Documents/random/rtl-comrade/modules/io.py) and [modules/funcs.py](/Users/daniellim/Documents/random/rtl-comrade/modules/funcs.py).

### Contracts

Contracts control input consumption policy.

- A contract must accept `id` and `ports` in `__init__`.
- If `__init__` also accepts `config`, it receives deserialized `contract_config`.
- A contract must expose `get_inputs()`.
- `get_inputs()` returns either `dict[str, Payload]` or `EndSentinel`.

The default contract supports default-valued inputs plus `persistent_inputs`. A custom zip-style contract example lives in [contracts/contracts.py](/Users/daniellim/Documents/random/rtl-comrade/contracts/contracts.py).

### Folder Manifests

Plugin folders can be loaded in two ways:

- With `config.yaml`, which explicitly maps file/class pairs to exported plugin names.
- Without a manifest, in which case all `.py` classes in the folder are discovered automatically.

The explicit-manifest form is already used in [modules/config.yaml](/Users/daniellim/Documents/random/rtl-comrade/modules/config.yaml) and [contracts/config.yaml](/Users/daniellim/Documents/random/rtl-comrade/contracts/config.yaml).

## Configuration Model

Graph YAML currently supports:

- `modules`: list of plugin folders
- `contracts`: list of contract folders
- `nodes`: graph nodes with `id`, `module`, `config`, optional `contract`, and `contract_config`
- `edges`: connections from `src.node/src.port` to `dst.node/dst.port`

Port handling today is mixed:

- source ports default to the string port name `"default"`
- destination ports may be a string or a 1-based positional index

The runtime now also validates `src.port` names against statically known emitted ports when the module structure analysis can determine them definitively. Preserve the current mixed source/destination port behavior unless you are intentionally refactoring the graph config API.

## What Is Stable vs. In Flux

Treat these as the current stable seams:

- YAML graph loading through `GraphConfig`
- plugin discovery through folder manifests
- module input and output inference through `ModuleStructure`
- contract-driven scheduling
- queue-based payload passing

Treat these as active prototype areas:

- typing quality and generic cleanup
- error handling and logging
- config/schema polish
- output-port semantics
- richer contract strategies
- tests, docs, and CLI ergonomics

## Contribution Guidance

- Keep changes small and local to the seam you are editing. The code is compact and reflection-heavy, so broad refactors are easy to break.
- Preserve the distinction between module behavior and contract behavior. Scheduling logic belongs in contracts, not modules.
- Prefer adding example graphs/modules/contracts when introducing a runtime feature; this repo currently relies heavily on executable examples.
- Be careful with end-sentinel behavior. Termination is part of the core design, and subtle changes can deadlock or prematurely stop graphs.
- Be careful when editing `structure.py`. The output-port analysis is intentionally conservative; dynamic port names are allowed, but they weaken what the graph validator can prove.
- When changing config shape or loader behavior, update both sample graphs and plugin manifests.
- Do not rely on `README.md` alone for architecture context; use the code as the primary source of truth.

## Gaps To Expect

- There is no committed test suite yet.
- `README.md` is effectively empty.
- Some files still contain TODOs and prototype-level comments.

## Practical Commands

Typical local entrypoints:

```bash
uv run rtl-comrade graph2.yaml
uv run python -m rtl_comrade graph2.yaml
```

The CLI still defaults to `graph.yaml` when no path is provided, but that file is not currently checked in, so pass an explicit graph path.

Python requirement is `>=3.11`, and the only declared runtime dependency today is `pyserde[yaml]`.

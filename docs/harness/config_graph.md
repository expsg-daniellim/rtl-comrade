# `config_graph.py`

Source: [src/rtl_comrade/config_graph.py](../../src/rtl_comrade/config_graph.py)

## Role

This file defines `GraphConfig`, the normalised intermediate type that sits between the serde-backed YAML schema (`GraphFileConfig` in `config.py`) and the runtime graph constructor (`Graph.from_config` in `graph.py`).

## See Also

- [README.md](README.md)
- [config.md](config.md) — `GraphFileConfig` and the raw config schema types
- [graph.md](graph.md)
- [loader.md](loader.md)

## Key Entry Points

- `GraphConfig.from_file(path)`: load a graph YAML file and produce a `GraphConfig`; called by `app.py` at startup for each registered command
- `GraphConfig.from_file_config(file_config)`: normalise an already-deserialized `GraphFileConfig` into a `GraphConfig`; called by `from_file` and directly in tests

## Main Types

- `GraphConfig` — normalised intermediate produced by `GraphConfig.from_file_config`; consumed by `Graph.from_config`

## GraphConfig Schema

Produced by `GraphConfig.from_file_config(file_config)`. Not serde-backed; constructed programmatically.

- `nodes`: copied unchanged from `GraphFileConfig`
- `modules`, `contracts`: `list[PluginFileConfig]` — produced by calling `resolve_paths` on the raw path strings from `GraphFileConfig`; see [loader.md](loader.md) for resolution semantics
- `edges`: only `GraphConfigSrcPort` sources; `GraphConfigSrcCLI` edges from `GraphFileConfig` are replaced with equivalent `GraphConfigSrcPort` edges pointing to synthetic `cli-{name}` node ids
- `cli_srcs`: `list[tuple[str, GraphConfigSrcCLI]]` — one entry per original CLI edge, in declaration order; each tuple is `(port_name, src)` where `port_name` is the synthetic node id (`cli-{src.cli}`) used in both the replacement edge and the virtual `Node` created by `Graph.from_config`
- `sig`: `inspect.Signature` built from the CLI sources; consumed by `Graph.construct_run` to expose a typer-compatible function signature

## Validation in `from_file_config`

`from_file_config` front-loads all structural checks that can be resolved from the config alone, before any plugin classes are loaded. Checks are fatal unless noted otherwise.

- **Duplicate node IDs**: two `nodes` entries share the same `id`
- **Blank CLI name**: a `GraphConfigSrcCLI` edge has `cli: ""`
- **Duplicate CLI name**: two CLI edges share the same `cli` value
- **CLI name conflicts with node ID**: the synthetic id `cli-{name}` would collide with an existing node id
- **Unused edge source** (warning, non-fatal): `edge.src.node` does not match any known node id; the edge is retained in `GraphConfig.edges` but emits `unused_edges`
- **Invalid edge destination**: `edge.dst.node` does not match any known node id
- **Cycle**: calls `validate_acyclic(nodes, edges)` on the node and edge lists; see [validation.md](validation.md)

Checks that require loaded plugin classes (invalid module/contract names, invalid port names, deadlock) are deferred to `Graph.from_config`; see [graph.md](graph.md).

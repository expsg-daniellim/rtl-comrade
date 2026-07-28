# `config_graph.py`

Source: [src/rtl_comrade/config_graph.py](../../src/rtl_comrade/config_graph.py)

## Role

This file defines `GraphConfig`, the normalised intermediate type that sits between the serde-backed YAML schema (`GraphFileConfig` in `config.py`) and the runtime graph constructor (`Graph.from_config` in `graph.py`).

## See Also

- [README.md](README.md)
- [config.md](config.md) — `GraphFileConfig` and the raw config schema types
- [graph.md](graph.md)
- [loader_plugin.md](loader_plugin.md)

## Main Responsibilities

- deserialise a `GraphFileConfig` into a `GraphConfig` via `from_file_config`
- resolve plugin paths relative to the graph file's directory
- validate graph structure before any plugin classes are loaded
- normalise CLI edges into a single `sig` and `cli_srcs`
- store `relative_path` for downstream use by `Node`

## Place In The System

`GraphConfig` is the intermediate between the YAML-backed `GraphFileConfig` and the fully-live `Graph`. It owns all structural checks that can be performed from config data alone, before any Python is imported.

## Key Behaviors

- structural validation is front-loaded in `from_file_config` so bad graphs are rejected before plugin classes are imported
- CLI edges are converted to synthetic node IDs (`cli-{name}`) so `Graph.from_config` sees a uniform edge list
- a `cli` name may recur across edges and node config to wire one CLI parameter to several destinations; recurrences must be identical descriptors and are deduplicated into a single `sig` parameter, while a conflicting recurrence is rejected
- `relative_path` flows through to each `Node` so module configs can use the `{graph}` prefix at construction time (see [node.md](node.md))
- unused source edges emit a warning and are retained, not dropped, so misconfigured graphs don't silently discard intended connections

## Key Entry Points

- `GraphConfig.from_file(path)`: load a graph YAML file and produce a `GraphConfig`; called by `app.py` at startup for each registered command. Takes `path` as a `Path` and passes `path.parent` as `relative_path` to `from_file_config`.
- `GraphConfig.from_file_config(file_config, relative_path=Path())`: normalise an already-deserialized `GraphFileConfig` into a `GraphConfig`; called by `from_file` and directly in tests. The `relative_path` argument is forwarded to `load_plugin_configs` for plugin discovery and stored on the returned `GraphConfig`.

## Main Types

- `GraphConfig` — normalised intermediate produced by `GraphConfig.from_file_config`; consumed by `Graph.from_config`

## GraphConfig Schema

Produced by `GraphConfig.from_file_config(file_config)`. Not serde-backed; constructed programmatically.

- `nodes`: copied unchanged from `GraphFileConfig`
- `modules`, `contracts`: `list[PluginFileConfig]` — produced by calling `load_plugin_configs(paths, relative_path)` on the `Path` objects from `GraphFileConfig`; plugin paths in the YAML are therefore resolved relative to the graph file's directory. See [loader_plugin.md](loader_plugin.md) for resolution semantics.
- `edges`: only `GraphConfigSrcPort` sources; `GraphConfigSrcCLI` edges from `GraphFileConfig` are replaced with equivalent `GraphConfigSrcPort` edges pointing to synthetic `cli-{name}` node ids
- `cli_srcs`: `list[tuple[str, GraphConfigSrcCLI]]` — one entry per original CLI edge, in declaration order; each tuple is `(port_name, src)` where `port_name` is the synthetic node id (`cli-{src.cli}`) used in both the replacement edge and the virtual `Node` created by `Graph.from_config`. A `cli` name reused across several edges produces one entry per edge, all sharing the same `port_name`; `Graph.from_config` keys virtual nodes by id, so the duplicates collapse to a single `ModuleCLI` node with one outgoing edge per destination (fan-out)
- `sig`: `inspect.Signature` built from the CLI sources; consumed by `Graph.construct_run` to expose a typer-compatible function signature. Each distinct `cli` name contributes exactly one parameter — the first occurrence registers it and later identical occurrences are deduplicated
- `relative_path`: the directory of the graph YAML file; forwarded to each `Node` by `Graph.from_config` so module configs can use the `{graph}` path prefix (see [node.md](node.md))
- `logging`: `LoggingConfig` — copied unchanged from `GraphFileConfig.logging`; resolved lazily by the `Graph.construct_run` closure via `config.logging.load(relative_path)` when the subcommand runs (see [loader_logger.md](loader_logger.md))

## Validation in `from_file_config`

`from_file_config` front-loads all structural checks that can be resolved from the config alone, before any plugin classes are loaded. Checks are fatal unless noted otherwise.

- **Duplicate node IDs**: two `nodes` entries share the same `id`
- **Blank CLI name**: a `GraphConfigSrcCLI` edge has `cli: ""`
- **CLI name conflicts with node ID**: the synthetic id `cli-{name}` would collide with an existing node id
- **Blank CLI name in node plugin**: an entry in any plugin's `cli` block has `cli: ""`
- **Conflicting CLI definition** (`cli_def_mismatch`): the same `cli` name appears more than once — across edges and all plugin `cli` blocks — with differing descriptor fields (`option`, `type`, `default`, `help`). A name is registered the first time it is seen; later occurrences are compared against that registration. An identical re-declaration is allowed and deduplicated (this is how one CLI parameter fans out to multiple destinations); a differing one is fatal
- **CLI config field shadows static config** (`cli_config_override`, warning, non-fatal): a key in a plugin's `cli` block also appears in that plugin's static `config`; the CLI value will override at construction time
- **Unused edge source** (warning, non-fatal): `edge.src.node` does not match any known node id; the edge is retained in `GraphConfig.edges` but emits `unused_edges`
- **Invalid edge destination**: `edge.dst.node` does not match any known node id
- **Cycle**: calls `validate_acyclic(nodes, edges)` on the node and edge lists; see [validation.md](validation.md)

Edge CLI sources and node plugin CLI parameters share a single name registry (a `dict` keyed by `cli` name). The first occurrence of a name registers its descriptor and appends one parameter to the shared `params` list; identical later occurrences are skipped, so the combined list — which produces the `sig` consumed by `Graph.construct_run` — holds exactly one parameter per distinct name. The `cli` blocks remain on the `GraphConfigNodePlugin` objects within `GraphConfig.nodes`; no separate collection field is added to `GraphConfig`.

The per-plugin work is handled by `GraphConfigNodePlugin.validate_cli_config(clis, params)`, called once per node for each of the four plugin fields (`module`, `contract`, `input_contract`, `output_contract`). It mutates `clis` and `params` in place — that shared registry is what makes a `cli` name reusable across plugins and edges — and returns a list of `LogEvent`s for any errors or warnings. The caller binds `index`, `node`, and a `config_type` contextvar around each call, so every log line identifies which plugin it came from; the log events themselves (`blank_cli`, `cli_def_mismatch`, `cli_config_override`) are shared across all four.

Checks that require loaded plugin classes (invalid module/contract names, invalid port names, deadlock) are deferred to `Graph.from_config`; see [graph.md](graph.md).

## Caveats

- checks that require loaded plugin classes (invalid module/contract names, invalid port names, deadlock) are deferred to `Graph.from_config`; a graph can pass `from_file_config` and still fail at runtime construction
- the parameter names in `sig` and the `cli_node.module.cli` values used for kwarg lookup in `Graph.construct_run` both derive from the CLI edge `cli` field but are set in separate places; if parameter name derivation ever changes here, `construct_run` must be updated to match or kwarg lookup will silently fail

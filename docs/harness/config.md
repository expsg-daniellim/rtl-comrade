# `config.py`

Source: [src/rtl_comrade/config.py](../../src/rtl_comrade/config.py)

## Role

This file defines the serde-backed graph configuration schema consumed by the harness.

## See Also

- [README.md](README.md)
- [config_graph.md](config_graph.md) — `GraphConfig`, the normalised intermediate produced from `GraphFileConfig`
- [graph.md](graph.md)
- [loader.md](loader.md)
- [validation.md](validation.md)

## Main Types

- `GraphFileConfig` — serde-backed YAML schema; the direct output of deserialising a graph file
- `GraphConfigNode`
- `GraphConfigEdge`
- `GraphConfigSrcPort`
- `GraphConfigSrcCLI`
- `GraphConfigDstPort`
- `InvalidCLIParameterError` — raised by `GraphConfigSrcCLI.as_param()` when a CLI parameter name is invalid

## Place In The System

This is the harness config boundary. `GraphFileConfig` is the typed shape of a graph YAML file. It is normalised into `GraphConfig` (see [config_graph.md](config_graph.md)) before being passed to `Graph.from_config`.

## GraphFileConfig Schema

- `modules`, `contracts`: `list[Path]` plugin paths from the YAML file
- `nodes`: node definitions with `id`, `module`, `config`, `contract`, and `contract_config`
- `edges`: edges with `src` (either a `GraphConfigSrcPort` or `GraphConfigSrcCLI`) and `dst`

`GraphConfigEdge.src` is a union deserialized with `Untagged` serde tagging; the schema is tried as `GraphConfigSrcPort` first, then `GraphConfigSrcCLI`.

`GraphConfigSrcCLI` fields: `cli` (parameter name), `option` (bool, default `True`), `type` (`"int"`, `"float"`, `"bool"`, or `"str"`, default `"str"`), `default` (optional), `help` (optional string).

## Port Conventions

- source ports default to `"default"`
- destination ports default to `1`
- destination ports may be given as either a string name or a 1-based positional index

## Caveats

- the mixed string-or-index destination port API is part of the current prototype and should be changed deliberately, not accidentally
- config validation is partly split between serde and later runtime checks in `graph.py`

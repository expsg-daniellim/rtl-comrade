# `config.py`

Source: [src/rtl_comrade/config.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/config.py)

## Role

This file defines the serde-backed graph configuration schema consumed by the harness.

## See Also

- [README.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/README.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [loader.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/loader.md)
- [validation.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/validation.md)

## Main Types

- `GraphConfig`
- `GraphConfigNode`
- `GraphConfigEdge`
- `GraphConfigSrcPort`
- `GraphConfigSrcCLI`
- `GraphConfigDstPort`

## Place In The System

This is the harness config boundary. It is the typed shape that sits between graph YAML and the runtime graph assembly in `graph.py`.

## Current Schema

- `modules`: list of plugin paths
- `contracts`: list of contract plugin paths
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

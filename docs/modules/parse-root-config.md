# `parse-root-config`

**Class:** `ParseRootConfigMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Reads the discovered root config YAML into a `RootConfig` (platforms, builders keyed by name, and the RTL register field). Uses a module-private serde type `RootConfigFile` for the on-disk shape.

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `path` | `Path` | the config file from [discover-config-file](discover-config-file.md) |

## Outputs

`default` — a `RootConfig`.

## Failure routing

`log.fatal` on any read error (`UnicodeDecodeError`, `FileNotFoundError`, `IsADirectoryError`, `PermissionError`, `OSError`) or parse error (`SerdeError`, YAML errors) — the run cannot proceed without the root config.

## Graph node

`parse-root`, contract `unit`. `RootConfig` fans out to [select-platform](select-platform.md), [resolve-builder](resolve-builder.md), [expand-sweep](expand-sweep.md), and [run-preproc](run-preproc.md).

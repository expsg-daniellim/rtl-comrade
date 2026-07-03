# `resolve-builder`

**Class:** `ResolveBuilderMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Selects the `RtlBuilderConfig` to build/sim with, either the CLI-supplied `builder` name or the platform's default.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `root_cfg` | `RootConfig` | — | parsed root config |
| `platform_cfg` | `PlatformConfig` | — | selected platform (supplies the fallback builder name) |
| `builder` | `str` | `""` | CLI override (`--builder`); empty means use the platform default |

## Outputs

`default` — the `RtlBuilderConfig`.

## Failure routing

`log.fatal` if the named builder is not among the configured builders.

## Graph node

`resolve-builder`, contract `unit`. The builder config is a persistent input to [filter-reglvl](filter-reglvl.md), [build-compile-cmd](build-compile-cmd.md), [resolve-seed](resolve-seed.md), and [build-sim-cmd](build-sim-cmd.md).

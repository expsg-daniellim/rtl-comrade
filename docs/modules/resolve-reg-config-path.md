# `resolve-reg-config-path`

**Class:** `ResolveRegConfigPathMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Resolves the path to the regression config. An explicit `reg_config` is resolved against the current working directory; an empty one falls back to `root_cfg.cfg_rtl_reg.path` (the root config's `reg-cfg-path`), resolved against the directory containing `root_config.yaml`.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `root_cfg` | `RootConfig` | — | parsed root config (supplies the fallback path) |
| `root_cfg_path` | `Path` | — | path to `root_config.yaml`; the fallback is joined onto its parent |
| `reg_config` | `str` | `""` | CLI override (`--reg-config`); empty means use the root config's path |

## Outputs

`default` — the resolved absolute `Path` to the regression config.

## Graph node

`resolve-reg-path`, contract `unit`, in the `regression` graph. `root_cfg` arrives from `parse-root`, `root_cfg_path` from `discover-root`, and `reg_config` from a CLI edge.

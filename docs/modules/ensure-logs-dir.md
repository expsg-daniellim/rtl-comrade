# `ensure-logs-dir`

**Class:** `EnsureLogsDirMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Creates `work_dir/logs_dir` (idempotently) and emits the path. This is where all compile/sim logs and randseeds land.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `work_dir` | `Path` | — | run working directory |
| `logs_dir` | `str` | `"logs"` | logs subdirectory name (CLI `--logs-dir`) |

## Outputs

`logs_dir` — the created directory `Path`. Note: the port is named `logs_dir`, not `default`.

## Failure routing

`log.fatal` (`logs_dir_create_failed`) on `OSError`.

## Graph node

`ensure-logs`, contract `unit`. The path is a persistent input to [build-compile-cmd](build-compile-cmd.md), [build-sim-cmd](build-sim-cmd.md), and [resolve-seed](resolve-seed.md).

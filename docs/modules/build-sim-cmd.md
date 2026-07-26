# `build-sim-cmd`

**Class:** `BuildSimCmdMod` (`modules/rtl_buddy/sim.py`)

[Back to index](index.md)

Assembles the sim invocation: the `simv` binary, the builder's run-time options (with the resolved seed), the test's plusdefines and plusargs. Also produces the timeout and a `RandSeed` record carrying the seed, the `.randseed` output path, and the argv (so [write-randseed](write-randseed.md) can detect hierarchical-instance-seed runs).

## Inputs

| Port | Type | Meaning |
|---|---|---|
| `test` | `TestConfig` | the run |
| `run_id` | `int \| None` | run id (log/seed filename suffix) |
| `simv` | `str` | sim binary |
| `seed` | `int` | resolved seed |
| `builder_cfg` | `RtlBuilderConfig` | run-time options |
| `builder_mode` | `str` | option-set selector |
| `logs_dir` | `Path` | log/seed output directory |

## Outputs

`test` — forwarded; `command` — a `Command` writing `<test><suffix>.log`/`.err`, consumed by [run-process](run-process.md); `timeout` — the sim timeout as a `float`; `randseed` — a `RandSeed(key, seed, randseed_path, argv)` feeding both [write-randseed](write-randseed.md) and [link-latest](link-latest.md).

## Behaviour

A per-test custom timeout emits a `custom_sim_timeout` `WARNING`.

## Graph node

`sim-build`, contract `keyed_join` (`key_field: key`, `persistent_inputs: [builder_cfg, builder_mode, logs_dir]`, `unwrap: true`, `ignore: [test, command, randseed]`). The `run_id`, `simv`, `seed` and `timeout` edges ride the wire as `KeyedValue`s; the contract unwraps the three inputs on the way in and keys the emitted `timeout` on the way out, so the module never handles the key.

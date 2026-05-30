# CLI surface and graph entry

## How a command becomes a graph

`rtl_comrade_config.yaml` maps a subcommand name to a graph file. Add:

```yaml
commands:
  test:
    path: "graphs/test.yaml"
    help: "Compile and simulate a SystemVerilog/UVM test suite."
```

The harness then exposes `uv run rtl-comrade test [options]`. Subcommand options come
from **CLI edges** in the graph YAML: the harness builds one virtual `ModuleCLI` node
(`cli-<name>`) per distinct `cli` name and wires it to a destination port. CLI edge types
are limited to the primitives `int | float | bool | str`.

## `rtl_buddy test` arguments → CLI edges

`rtl_buddy`'s `test` command (`do_cmd_test`) plus the relevant global options
(`root_options`) become these CLI edges:

| rtl_buddy arg | flag | type | default | CLI edge `cli` name | feeds node |
|---|---|---|---|---|---|
| `test_config` | `-c/--test-config` | str | `tests.yaml` | `test_config` | `parse-suite-config` |
| `test_name` | positional (optional) | str | `""` (= all) | `test_name` | `select-tests` |
| `list_tests` | `--list` | bool | `false` | `list` | `route-list-mode` |
| `rnd_new` | `-n/--rnd-new` | bool | `false` | `rnd_new` | `derive-seed-mode` |
| `rnd_last` | `-l/--rnd-last` | bool | `false` | `rnd_last` | `derive-seed-mode` |
| `rtl_builder_mode` (global) | `-M/--builder-mode` | str | `debug` | `builder_mode` | `build-compile-cmd`, `build-sim-cmd` |
| `builder_override` (global) | `-B/--builder` | str | `""` | `builder` | `resolve-builder` |
| `run_depth` (global) | `-E/--early-stop` | str | `post` | `early_stop` | the `early-stop-gate` nodes |

Notes and decisions (see [07](07-ambiguities-and-assumptions.md)):

- **`test_name` is a true optional positional** (CLI edge `option: false`, `default: ""`),
  matching rtl_buddy's CLI surface. An empty value means "all tests".
- **Seed mode from two bools.** `rtl_buddy` derives `SeedMode` from `rnd_new`/`rnd_last`
  (`rnd_new` wins). A tiny `derive-seed-mode` module turns the two bool CLI edges into a
  single `seed_mode` value (`NEW`/`REPLAY`/`DEFAULT`) used by `resolve-seed`. Alternatively
  expose one `--seed-mode` string edge and drop the module.
- **`--early-stop` is a string** (`pre`/`comp`/`sim`/`post`). Each `early-stop-gate` node
  compares it (as an ordered phase) against its own phase. It is a single value reused by
  all gates, so it is wired as a **persistent** input to each gate.
- **`--debug`/`--color`** from `rtl_buddy`'s root options are logging concerns. `rtl-comrade`
  already owns logging via its global `--level` flag and structlog setup, so these are
  intentionally dropped (see [07](07-ambiguities-and-assumptions.md)). `--builder-mode`,
  `--builder`, and `--early-stop` are genuinely test-affecting, so they survive as CLI edges.
- `rtl_buddy` always prepends `.` to `$PATH` so a simulator in the CWD is found. The
  `run-process` module should replicate this (or a setup node like `resolve-builder`), since
  it is load-bearing for `verilator`/`simv` discovery.

## What the harness does NOT give us

`rtl-comrade` subcommands have no native concept of "global options that apply to every
subcommand" beyond `--level` and `--config-file`. Anything `rtl_buddy` put on its root
callback (builder, early-stop, debug) must be re-declared per graph as CLI edges. For
`randtest`/`regression` (sibling graphs reusing this module catalog), the same CLI edges
are re-declared with the extra args those commands need (`rnd_cnt`, `reg_level`,
`start_level`).

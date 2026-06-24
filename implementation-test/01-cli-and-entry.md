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

All `rtl_buddy src` citations are anchored to rtl_buddy `v1.4.0` (commit `a69d962`; see
[00 — Source baseline](00-overview.md)). Flags live in `rtl_buddy/src/rtl_buddy/rtl_buddy.py`,
in either `do_cmd_test` (`:166-173`) or the global `root_options` (`:114-123`).

| rtl_buddy arg | flag | type | default | CLI edge `cli` name | feeds node | rtl_buddy src |
|---|---|---|---|---|---|---|
| `test_config` | `-c/--test-config` | str | `tests.yaml` | `test_config` | `parse-suite-config` (resolves it against CWD) | `rtl_buddy.py:167` |
| *(none)* | `-L/--logs-dir` | str | `logs` | `logs_dir` | `ensure-logs-dir`, `build-compile-cmd`, `build-sim-cmd`, `resolve-seed` | *(new — Notable divergence; `"logs"` literal at `tools/vlog_sim.py:55`)* |
| `test_name` | positional (optional) | str | `""` (= all) | `test_name` | `select-tests` | `rtl_buddy.py:168` |
| `list_tests` | `--list` | bool | `false` | `list` | `route-list-mode` | `rtl_buddy.py:169` |
| `rnd_new` | `-n/--rnd-new` | bool | `false` | `rnd_new` | `derive-seed-mode` | `rtl_buddy.py:171` |
| `rnd_last` | `-l/--rnd-last` | bool | `false` | `rnd_last` | `derive-seed-mode` | `rtl_buddy.py:172` |
| `rtl_builder_mode` (global) | `-M/--builder-mode` | str | `debug` | `builder_mode` | `build-compile-cmd`, `build-sim-cmd` | `rtl_buddy.py:119` |
| `builder_override` (global) | `-B/--builder` | str | `""` | `builder` | `resolve-builder` | `rtl_buddy.py:120` (callback `cb_builder` `:70-81`) |
| `run_depth` (global) | `-E/--early-stop` | str | `post` | `early_stop` | the `early-stop-gate` nodes | `rtl_buddy.py:121` |

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
- **`-L/--logs-dir` is a small Notable divergence from `rtl_buddy`.** `rtl_buddy` hard-codes
  `"logs"` (`rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55`); this plan keeps the same default
  but exposes the path as a CLI override so the artefact directory can be relocated without
  chdir gymnastics. The directory is materialised by the `ensure-logs-dir` setup node and
  consumed by `build-compile-cmd` / `build-sim-cmd` / `resolve-seed`. See
  [07 settled 26](07-ambiguities-and-assumptions.md).

## Where to invoke `rtl-comrade test` from

`rtl-comrade test` and `rtl-comrade randtest` follow `rtl_buddy`'s convention: **invoke
from the suite directory** (the directory that contains `tests.yaml`). `rtl_buddy`'s
`do_cmd_test` never `chdir`s — only `do_rtl_regression` does, per-suite
(`rtl_buddy/src/rtl_buddy/rtl_buddy.py:404`). The validation example in
`rtl_buddy/AGENTS.md` makes this concrete: `cd .../verif && python -m rtl_buddy test
basic`.

In the plain `test` and `randtest` graphs, `run.f`, `obj_dir_<tag>/`, `logs/` (or whatever
`--logs-dir` resolves to), the `test.*` symlinks, and `HierInstanceSeed.txt` all land in the
artefact base `work_dir`, which a zero-input [`work-dir`](03-module-catalog.md) setup node sets to
the **invocation CWD** (`Path.cwd().resolve()`) — faithful to rtl_buddy's `do_cmd_test`, which never
`chdir`s (run here, output here). `-c <dir>/tests.yaml` only *locates* the config; artefacts still
land in CWD and relative paths in the config are CWD-relative — the conventional shell semantics, no
auto-relocation. A missing config file surfaces in `parse-suite-config` (which opens it) as a
`log.fatal`; there is no separate resolve node and no CWD-mismatch abort. The `regression` graph does
**not** wire `work-dir` — it sources a per-suite `work_dir` from each suite's directory (mirroring
`do_rtl_regression`'s per-suite `chdir`). See [07 settled 24](07-ambiguities-and-assumptions.md)
for the full rationale.

The artefact directory itself is materialised by an [`ensure-logs-dir`](03-module-catalog.md)
setup node fed by the CLI `logs_dir` edge (default `"logs"` — parity with rtl_buddy). It
runs once at startup, rooting `logs/` on `work-dir`'s `work_dir`, and emits the resolved
`logs_dir` `Path`; the subprocess composers block on that (first-run-required) value before
building a command, so the `mkdir` is ordered ahead of every redirect by the data edge itself.
The `$PATH` fix is sequenced separately by `prepend-cwd-path → run-process.env_ready`
(`required: true`). See [07 settled 25/26](07-ambiguities-and-assumptions.md).

## What the harness does NOT give us

`rtl-comrade` subcommands have no native concept of "global options that apply to every
subcommand" beyond `--level` and `--config-file`. Anything `rtl_buddy` put on its root
callback (builder, early-stop, debug) must be re-declared per graph as CLI edges. For
`randtest`/`regression` (sibling graphs reusing this module catalog), the same CLI edges
are re-declared with the extra args those commands need (`rnd_cnt`, `reg_level`,
`start_level`).

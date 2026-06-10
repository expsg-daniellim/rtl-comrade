# Spec 11: Graph YAML and manifest registration

**Depends on:** specs 02–10 (all contracts + modules).
**References:** [06 — `graphs/test.yaml`](../06-graph-yaml.md).

## Goal

Assemble the test graph YAML, finalise plugin manifests, and register the `test`
subcommand in `rtl_comrade_config.yaml`.

## Deliverables

- **`graphs/test.yaml`** — verbatim from [06](../06-graph-yaml.md): all nodes (including the
  `git-status` setup node; **no** `fan-in`/`agg` nodes — removed by TODO #15), CLI edges
  (including `test_name` as positional with `option: false, default: ""`), setup chain,
  persistent-config fan-out, list-mode routing, main-line continue ports, the **unwired**
  terminal ports (no edges), and the `logging` block that wires the `SummaryHandler` plugin.
- **`graphs/log/summary.py`** — the `SummaryHandler` + `drop_summary_events` logging plugin
  (spec 10), referenced by `path`/`name` from the `logging` block.
- **`modules/config.yaml`** — full manifest from [06](../06-graph-yaml.md) covering every
  module from specs 03–10 (`run-process`, the setup chain incl. `git-status`,
  selection/expansion, prep, compile cycle, sim cycle, post, control).
- **`contracts/config.yaml`** — the `any` registration from spec 02 (registered for reuse but
  **unwired** in `test`). There is **no** `serial_acquire` contract: the interim parallel-safety
  lock shim was removed (TODO #30) in favour of per-tag artefact naming — see
  [06](../06-graph-yaml.md) and [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
- **`rtl_comrade_config.yaml`** — add:
  ```yaml
  commands:
    test:
      path: "graphs/test.yaml"
      help: "Compile and simulate a SystemVerilog/UVM test suite."
  ```

## Acceptance criteria

- `uv run rtl-comrade --help` lists `test` with the help string.
- `uv run rtl-comrade test --help` lists every CLI edge from [06](../06-graph-yaml.md)
  (`test_config`, `builder`, `test_name` positional, `list`, `rnd_new`, `rnd_last`,
  `builder_mode`, `early_stop`) with correct types/defaults.
- Graph loads without validation errors — `Graph.from_file("graphs/test.yaml")` succeeds.
- `validation.py` reports no cycles or overloaded inputs.

## Notes

This spec is mostly assembly — copy [06](../06-graph-yaml.md) faithfully. If any
node/port name diverged between [03](../03-module-catalog.md) and what got built in specs
04–10, reconcile here (prefer matching the actual module signatures over the plan).

The 13 terminal ports are **unwired** (TODO #15) — there is no `fan-in`/`agg` node. Each
terminal node logs a `test_result` event; the `SummaryHandler` plugin (declared in the
`logging` block) renders the table in `finalise()`, and per-emission `log.error` drives the
exit code. `validation.py` reports the unwired ports as `no_destination` at INFO, not errors.
See [spec 10](10-control-aggregate-modules.md) for the plugin.

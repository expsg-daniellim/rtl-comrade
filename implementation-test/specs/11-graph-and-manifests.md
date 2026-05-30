# Spec 11: Graph YAML and manifest registration

**Depends on:** specs 02–10 (all contracts + modules).
**References:** [06 — `graphs/test.yaml`](../06-graph-yaml.md).

## Goal

Assemble the test graph YAML, finalise plugin manifests, and register the `test`
subcommand in `rtl_comrade_config.yaml`.

## Deliverables

- **`graphs/test.yaml`** — verbatim from [06](../06-graph-yaml.md): all 22 nodes, CLI
  edges (including `test_name` as positional with `option: false, default: ""`), setup
  chain, persistent-config fan-out, list-mode routing, main-line continue ports, and the
  eight terminal-port edges into `agg`.
- **`modules/config.yaml`** — full manifest from [06](../06-graph-yaml.md) covering every
  module from specs 03–10 (`run-process`, the setup chain, selection/expansion, prep,
  compile cycle, sim cycle, post, control/aggregate).
- **`contracts/config.yaml`** — `merge` registration from spec 02.
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

If the framework verification in spec 00 found that `**kwargs` port inference doesn't
work, declare `agg`'s eight ports explicitly in the module (per spec 10's notes) and
adjust this graph accordingly — the edges already name each port.

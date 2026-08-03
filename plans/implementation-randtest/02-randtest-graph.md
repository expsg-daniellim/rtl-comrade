# Spec 02: Graph YAML, manifest, and command registration

**Depends on:** [01](01-derive-randtest-runs.md) (`derive-randtest-runs` — the one new module this graph wires).
**References:** [00-overview](00-overview.md) — graph delta, CLI surface, carry-over list; `graphs/test.yaml` — the baseline graph this is derived from; `docs/harness_configs/graph.md` (nodes, edges, CLI edge sources); `docs/harness_configs/rtl_comrade_config.md` (registering subcommands).

## Before you start

Read `docs/harness_configs/graph.md` and `docs/harness_configs/rtl_comrade_config.md`. This spec assembles `graphs/randtest.yaml` by applying the delta from [00-overview](00-overview.md) to `graphs/test.yaml`. It defines no new module.

## Goal

Create the `randtest.yaml` graph file, register the `randtest` subcommand, and land the manifest entry from [spec 01](01-derive-randtest-runs.md). The graph must be structurally identical to `test.yaml` except for the three documented deltas (seed derivation, no list mode, required test name).

## Graph construction

Copy `test.yaml` and apply the delta from [00-overview](00-overview.md):

### Nodes

Remove:

```yaml
- { id: seed-mode,  module: derive-seed-mode, contract: unit }
- { id: route-list, module: flag-gate,         contract: unit }
- { id: list-names, module: list-test-names,   contract: default }
```

Add:

```yaml
- { id: derive-runs, module: derive-randtest-runs, contract: unit }
```

### Edges

Remove the `seed-mode` wiring (two CLI inputs, one output), the `list` CLI edge, and the four `route-list` edges (input from `parse-suite`, two output arms to `list-names` and `select`).

Add `derive-runs` CLI inputs and outputs:

```yaml
- { src: { cli: rnd_cnt, option: false, type: int, default: 2 }, dst: { node: derive-runs, port: rnd_cnt } }
- { src: { cli: rnd_rpt, type: int, default: -1 },              dst: { node: derive-runs, port: rnd_rpt } }
- { src: { node: derive-runs, port: run_ids },   dst: { node: runs, port: run_ids } }
- { src: { node: derive-runs, port: seed_mode }, dst: { node: seed, port: seed_mode } }
```

Add direct `parse-suite` → `select` edge (replacing the `route-list` bypass):

```yaml
- { src: { node: parse-suite }, dst: { node: select, port: suite_cfg } }
```

Change `test_name` — remove `default` to make it required:

```yaml
- { src: { cli: test_name, option: false, type: str }, dst: { node: select, port: test_name } }
# (was: { cli: test_name, option: false, type: str, default: "" })
```

### CLI parameters

The full CLI surface is documented in [00-overview § CLI surface](00-overview.md#cli-surface). Key differences from `test`:

- `rnd_new`, `rnd_last`, `list` are **absent** — their CLI edges do not exist.
- `rnd_cnt` is a positional (second, after `test_name`) with default `2`.
- `rnd_rpt` is an option (`-r/--rnd-rpt`) with default `-1`.
- `test_name` is a required positional (no `default` field).

### Everything else

All other nodes, edges, contracts, `persistent_inputs` configs, fan-out edges, and the `logging:` block carry over unchanged from `test.yaml`. The carry-over list in [00-overview](00-overview.md#everything-else) is exhaustive — if a node or edge from `test.yaml` is not mentioned in the delta, it appears verbatim in `randtest.yaml`.

## Command registration

Add to `rtl_comrade_config.yaml`:

```yaml
  randtest:
    path: "graphs/randtest.yaml"
    help: "Random-seed testing of a single test."
```

## Manifest

The manifest entry from [spec 01](01-derive-randtest-runs.md) must be landed in `modules/config.yaml` before the graph can load. Every other module the graph references (`flag-gate`, `derive-seed-mode`, `list-test-names` excepted — they are removed) already has a manifest entry from the `test` graph's implementation.

## Tests

### Graph-level tests

- `Graph.from_file("graphs/randtest.yaml")` → loads without error; every node's module name resolves against `modules/config.yaml`.
- Validation reports **no** cycles, **no** overloaded inputs, **no** `missing_required_inputs`, **no** `unknown_persistent_ports`.
- The graph contains `derive-runs` and does **not** contain `seed-mode`, `route-list`, or `list-names`.

### E2E tests

Using the existing fixture project (`tests/e2e/fixtures/proj/`).

- `rtl-comrade randtest <test_name>` — runs with default `rnd_cnt=2`, produces sim outputs for run IDs 1 and 2.
- `rtl-comrade randtest <test_name> 3` — runs with `rnd_cnt=3`.
- `rtl-comrade randtest <test_name> --rnd-rpt 1` — replays seed from run 1 (requires a prior `randtest` run to have written the `.randseed` file).
- `rtl-comrade randtest` (no test name) — errors with a missing-argument message (required positional).

### CLI tests

- `uv run rtl-comrade --help` → output lists `randtest` with the help string `"Random-seed testing of a single test."`.
- `uv run rtl-comrade randtest --help` → output lists every CLI parameter from the [overview table](00-overview.md#cli-surface) with correct types and defaults; `rnd_new`, `rnd_last`, `list` are absent.

## Acceptance criteria

- All test stages pass (`docs/testing.md`).
- `graphs/randtest.yaml` loads without structural validation errors.
- `randtest` appears in `rtl-comrade --help`.
- A basic `randtest` run against the fixture project completes with the expected number of sim invocations.
- The graph is structurally identical to `test.yaml` except for the documented deltas — no accidental omissions or additions.
- `rnd_new`, `rnd_last`, and `list` do not appear anywhere in the graph.

## Constraints

- **Delta only.** The graph file is `test.yaml` plus the documented delta — do not reorganise, rename, or reorder anything that carries over unchanged.
- **No new modules.** This spec wires [spec 01](01-derive-randtest-runs.md)'s module and removes three existing nodes. No other module is added or modified.
- **No list mode.** The `route-list` / `list-names` / `list` CLI edge set is absent, not defaulted-off.
- **Required `test_name`.** Enforced by omitting `default` from the CLI edge descriptor, not by validation code.

## Docs

Update `docs/graphs/index.md` to list the `randtest` graph. Add `docs/graphs/randtest.md` following the structure of `docs/graphs/test.md`, documenting only the delta from `test`. Add `docs/graphs/randtest-dataflow-diagram.md` containing the mermaid diagram from [00-overview § Full graph](00-overview.md#full-graph). Follow `docs/creating-documentation.md`.

# Spec 05: graph YAML, manifest, and command registration

**Depends on:** [01](01-resolve-reg-config-path.md), [02](02-parse-reg-config.md), [03](03-suite-key-prefix.md), [04](04-extract-suite-dir.md) — all new/changed modules this graph wires.
**References:** [00-overview](00-overview.md) — graph delta, CLI surface, carry-over list; `graphs/test.yaml` — the baseline graph this is derived from; `docs/harness_configs/graph.md` (nodes, edges, CLI edge sources); `docs/harness_configs/rtl_comrade_config.md` (registering subcommands).

## Before you start

Read `docs/harness_configs/graph.md` and `docs/harness_configs/rtl_comrade_config.md`. This spec assembles `graphs/regression.yaml` by applying the delta from [00-overview](00-overview.md) to `graphs/test.yaml`. It defines no new module.

## Goal

Create the `regression.yaml` graph file, register the `regression` subcommand, and wire the modules from specs 01–04. The graph must be structurally identical to `test.yaml` except for the documented deltas.

## Graph construction

Copy `test.yaml` and apply the delta from [00-overview](00-overview.md):

### Nodes

Remove:

```yaml
- { id: seed-mode,  module: derive-seed-mode,  contract: unit }
- { id: route-list, module: flag-gate,          contract: unit }
- { id: list-names, module: list-test-names,    contract: default }
- { id: work-dir,   module: work-dir,           contract: default }
- { id: ensure-logs, module: ensure-logs-dir,   contract: ... }
```

Add:

```yaml
- { id: resolve-reg-path, module: resolve-reg-config-path, contract: unit }
- { id: parse-reg, module: parse-reg-config, contract: default }
- id: const-seed-mode
  module:
    name: constant
    config:
      type: "modules.rtl_buddy.schema.seed_mode:SeedMode"
      value: "DEFAULT"
  contract: default
- id: extract-dir
  module: { name: extract-suite-dir }
  contract: { name: default, config: { persistent_inputs: [logs_dir] } }
- id: extract-dir-post
  module: { name: extract-suite-dir }
  contract: { name: default, config: { persistent_inputs: [logs_dir] } }
```

Change:

```yaml
- id: parse-suite
  module: { name: parse-suite-config, config: { prefix_suite: true } }
  contract: default
# (was: module: parse-suite-config, contract: unit)
```

Remove `work_dir`, `base_dir`, and/or `logs_dir` from `persistent_inputs` on `cc-build`, `cc-run`, `sim-build`, `seed`, `sim-run`, `randseed`, `link-latest`, `fl-tb`, `fl-norm`, `fl-path` per [00-overview § Nodes changed](00-overview.md#nodes-changed).

### Edges

Remove all edges listed in [00-overview § Edges removed](00-overview.md#edges-removed).

Add all edges listed in [00-overview § Edges added](00-overview.md#edges-added): suite stream, level filtering, seed mode, `extract-dir` pre-fan-out, `extract-dir-post` post-fan-out.

### CLI parameters

The full CLI surface is documented in [00-overview § CLI surface](00-overview.md#cli-surface). Key differences from `test`:

- `test_name`, `list`, `rnd_new`, `rnd_last`, `test_config` are **absent**.
- `reg_config` (`-c/--reg-config`) with default `""`.
- `reg_level` (`-l/--reg-level`) and `start_level` (`-s/--start-level`) with default `0`.
- `builder_mode` default changes from `"debug"` to `"reg"`.

### Everything else

All other nodes, edges, contracts, fan-out edges, and the `logging:` block carry over unchanged from `test.yaml`. The carry-over list in [00-overview § Everything else](00-overview.md#everything-else) is exhaustive — if a node or edge from `test.yaml` is not mentioned in the delta, it appears verbatim in `regression.yaml`.

## Command registration

Add to `rtl_comrade_config.yaml`:

```yaml
  regression:
    path: "graphs/regression.yaml"
    help: "Run regression suites with level filtering."
```

## Tests

### Graph-level tests

- `Graph.from_file("graphs/regression.yaml")` → loads without error; every node's module name resolves against `modules/config.yaml`.
- Validation reports **no** cycles, **no** overloaded inputs, **no** `missing_required_inputs`, **no** `unknown_persistent_ports`.
- The graph contains `resolve-reg-path`, `parse-reg`, `const-seed-mode`, `extract-dir`, `extract-dir-post` and does **not** contain `seed-mode`, `route-list`, `list-names`, `work-dir`, `ensure-logs`.

### E2E tests

Using the existing fixture project. The fixture already has a `design/regression.yaml` (`tests/e2e/fixtures/proj/design/regression.yaml`) referencing `../verif/sandbox/tests.yaml`.

- `rtl-comrade regression` — runs with default `reg_config=""` (derived from root config), `reg_level=0`, `start_level=0`. All tests from all suites run.
- `rtl-comrade regression -c design/regression.yaml` — explicit reg config path, same result.
- `rtl-comrade regression -l 1` — filters tests to regression level ≤ 1.
- `rtl-comrade regression -s 2` — filters tests to regression level ≥ 2.
- `rtl-comrade regression -M debug` — overrides builder mode from the default `reg`.

### CLI tests

- `uv run rtl-comrade --help` → output lists `regression` with the help string `"Run regression suites with level filtering."`.
- `uv run rtl-comrade regression --help` → output lists every CLI parameter from the [overview table](00-overview.md#cli-surface) with correct types and defaults; `test_name`, `list`, `rnd_new`, `rnd_last`, `test_config` are absent.

## Acceptance criteria

- All test stages pass (`docs/testing.md`).
- `graphs/regression.yaml` loads without structural validation errors.
- `regression` appears in `rtl-comrade --help`.
- A basic `regression` run against the fixture project completes, creates per-suite `logs/` directories, produces a summary table with suite-prefixed keys, and returns exit code 0 when all tests pass.
- Level filtering correctly includes/excludes tests.
- `builder_mode` defaults to `"reg"`.
- The graph is structurally identical to `test.yaml` except for the documented deltas — no accidental omissions or additions.
- `rnd_new`, `rnd_last`, `list`, `test_name`, and `test_config` do not appear anywhere in the graph.

## Constraints

- **Delta only.** The graph file is `test.yaml` plus the documented delta — do not reorganise, rename, or reorder anything that carries over unchanged.
- **No new modules.** This spec wires specs 01–04's modules, adds a `constant` instance, and removes five existing nodes. No other module is added or modified.
- **No list mode.** The `route-list` / `list-names` / `list` CLI edge set is absent, not defaulted-off.
- **No `work-dir` or `ensure-logs`.** Their roles are absorbed by `extract-dir` and `extract-dir-post`.

## Docs

Update `docs/graphs/index.md` to list the `regression` graph. Add `docs/graphs/regression.md` following the structure of `docs/graphs/test.md`, documenting only the delta from `test`. Add `docs/graphs/regression-dataflow-diagram.md` containing the mermaid diagram from [00-overview § Full graph](00-overview.md#full-graph). Follow `docs/creating-documentation.md`.

# Spec 11: Graph YAML and manifest registration

**Depends on:** specs 02–10 (all contracts + modules).
**References:** [06 — `graphs/test.yaml`](../06-graph-yaml.md).

## Before you start

Read the harness config-file docs this spec assembles: `docs/harness_configs/graph.md` (nodes,
edges, node/CLI edge sources, and the "Logging configuration" section that wires the
`SummaryProcessor` plugin), `docs/harness_configs/plugin_manifest.md` (the module/contract
`config.yaml` shape), and `docs/harness_configs/rtl_comrade_config.md` (registering the `test`
subcommand). `docs/harness/validation.md` explains the static checks the acceptance criteria rely on
(cycles, overloaded inputs). The `no_destination` INFO log for the unwired terminal ports is a
**runtime** node emission, not a static check — see `docs/harness/node.md` ("Key Behaviors").
[`06 — graphs/test.yaml`](../06-graph-yaml.md) is the design source to copy verbatim. This spec
is the sole owner of `graphs/test.yaml`, `modules/config.yaml`, `contracts/config.yaml`, and the
`rtl_comrade_config.yaml` entry — no sibling specs append to those files.

## Goal

Assemble the test graph YAML, finalise plugin manifests, and register the `test`
subcommand in `rtl_comrade_config.yaml`.

## Deliverables

- **`graphs/test.yaml`** — verbatim from [06](../06-graph-yaml.md): all nodes (including the
  `git-status` setup node), CLI edges
  (including `test_name` as positional with `option: false, default: ""`), setup chain,
  persistent-config fan-out, list-mode routing, main-line continue ports, the **unwired**
  terminal ports (no edges), and the `logging` block that wires the `SummaryProcessor` plugin.
- **`graphs/log/summary.py`** — the `SummaryProcessor` logging plugin (a single structlog
  processor; spec 10), referenced by `path`/`name` from the `logging` block.
- **`modules/config.yaml`** — full manifest covering every module from specs 03–10
  (`run-process`, the setup chain incl. `git-status`, selection/expansion, prep, compile cycle,
  sim cycle, post, control). The four file blocks each child spec contributes to (verbatim from
  [06](../06-graph-yaml.md)):
  ```yaml
  - file: rtl_buddy/setup.py
    plugins:
    - { name: discover-config-file, class_name: DiscoverConfigFileMod }
    - { name: prepend-cwd-path,     class_name: PrependCwdPathMod }
    - { name: parse-root-config,    class_name: ParseRootConfigMod }
    - { name: select-platform,      class_name: SelectPlatformMod }
    - { name: resolve-builder,      class_name: ResolveBuilderMod }
    - { name: check-suite-cwd,      class_name: CheckSuiteCwdMod }
    - { name: ensure-logs-dir,      class_name: EnsureLogsDirMod }
    - { name: parse-suite-config,   class_name: ParseSuiteConfigMod }
    - { name: derive-seed-mode,     class_name: DeriveSeedModeMod }
    - { name: git-status,           class_name: GitStatusMod }
    - { name: route-list-mode,      class_name: RouteListModeMod }
    - { name: list-test-names,      class_name: ListTestNamesMod }
    - { name: select-tests,         class_name: SelectTestsMod }
    - { name: filter-reglvl,        class_name: FilterRegLvlMod }
    - { name: load-model,           class_name: LoadModelMod }
    - { name: expand-sweep,         class_name: ExpandSweepMod }
  - file: rtl_buddy/build.py
    plugins:
    - { name: run-preproc,       class_name: RunPreprocMod }
    - { name: write-filelist,    class_name: WriteFilelistMod }
    - { name: build-compile-cmd, class_name: BuildCompileCmdMod }
    - { name: run-process,       class_name: RunProcessMod }
    - { name: interpret-compile, class_name: InterpretCompileMod }
  - file: rtl_buddy/sim.py
    plugins:
    - { name: expand-runs,       class_name: ExpandRunsMod }
    - { name: resolve-seed,      class_name: ResolveSeedMod }
    - { name: build-sim-cmd,     class_name: BuildSimCmdMod }
    - { name: write-randseed,    class_name: WriteRandseedMod }
    - { name: link-latest,       class_name: LinkLatestMod }
    - { name: interpret-sim,     class_name: InterpretSimMod }
    - { name: route-post,        class_name: RoutePostMod }
    - { name: parse-log,         class_name: ParseLogMod }
    - { name: parse-uvm-log,     class_name: ParseUvmLogMod }
  - file: rtl_buddy/control.py
    plugins:
    - { name: early-stop-gate,   class_name: EarlyStopGateMod }
  ```
- **`contracts/config.yaml`** — the `any` registration from spec 02 (registered for reuse but
  **unwired** in `test`). Parallel safety comes from per-tag artefact naming — see
  [06](../06-graph-yaml.md) and
  [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
  ```yaml
  - file: any.py
    plugins:
    - { name: any, class_name: AnyContract }
  ```
- **`rtl_comrade_config.yaml`** — add:
  ```yaml
  commands:
    test:
      path: "graphs/test.yaml"
      help: "Compile and simulate a SystemVerilog/UVM test suite."
  ```

## Tests

Graph-assembly checks in `tests/test_graph_assembly.py` (or similar) — the inputs are the
committed YAML files, the expected outputs are load/validation outcomes. Fixtures: the
harness `Graph.from_file` / `validation.py` API; a CLI runner (subprocess or the harness's
test runner) for the `--help` cases.

- `Graph.from_file("graphs/test.yaml")` → loads without error; every node `class_name`
  resolves against `modules/config.yaml` and every contract against `contracts/config.yaml`
  (boundary: no dangling manifest reference).
- `validation.py` on the loaded graph → reports **no** cycles and **no** overloaded inputs
  (single-source-per-port holds).
- Running the graph → each emission on an unwired terminal port logs `no_destination` at INFO
  (a `node.py` runtime emission), **not** an error or a validation failure (boundary:
  unwired-by-design terminal ports). This is runtime behavior, not a `validation.py` check.
- `uv run rtl-comrade --help` → output lists `test` with the help string `"Compile and
  simulate a SystemVerilog/UVM test suite."`.
- `uv run rtl-comrade test --help` → output lists every CLI edge (`test_config`, `logs_dir`
  type `str` default `"logs"`, `builder`, `test_name` positional with `option: false, default: ""`,
  `list`, `rnd_new`, `rnd_last`, `builder_mode`, `early_stop`) with the types/defaults from
  [06](../06-graph-yaml.md).

## Acceptance criteria

- `uv run rtl-comrade --help` lists `test` with the help string.
- `uv run rtl-comrade test --help` lists every CLI edge from [06](../06-graph-yaml.md)
  (`test_config`, `logs_dir` type `str` default `"logs"`, `builder`, `test_name` positional,
  `list`, `rnd_new`, `rnd_last`, `builder_mode`, `early_stop`) with correct types/defaults.
- Graph loads without validation errors — `Graph.from_file("graphs/test.yaml")` succeeds.
- `validation.py` reports no cycles or overloaded inputs.
- Every module name registered in `modules/config.yaml` and every contract name in
  `contracts/config.yaml` resolves to its declared class (this spec is the central owner of
  the registry-resolvability assertion the module specs 03–10 reference).

## Constraints

- Copy [06](../06-graph-yaml.md) **verbatim**; if a node/port name drifted between
  [03](../03-module-catalog.md) and what specs 04–10 actually built, reconcile **toward the
  built module signatures**, not the plan.
- The 13 terminal ports stay **unwired**. At runtime the node logs `no_destination` at INFO for
  them, **not** errors; this is a `node.py` runtime emission, not a `validation.py` static check.
- Register the `any` contract for reuse but leave it **unwired** in `test`.
- The summary is wired only via the `logging` block (`graphs/log/summary.py` → `SummaryProcessor`);
  it is **not** a module manifest entry.
- The assembled graph must load with no cycles and no overloaded inputs (single-source-per-port).

## Notes

This spec is mostly assembly — copy [06](../06-graph-yaml.md) faithfully. If any
node/port name diverged between [03](../03-module-catalog.md) and what got built in specs
04–10, reconcile here (prefer matching the actual module signatures over the plan).

The 13 terminal ports are **unwired**. Each
terminal node logs a `test_result` event; the `SummaryProcessor` plugin (declared in the
`logging` block) accumulates the rows and renders the table in `finalise()`, and per-emission
`log.error` drives the exit code. At runtime the node logs the unwired ports as `no_destination` at INFO, not errors (a `node.py` runtime emission, not a `validation.py` check).
See [spec 10c](10c-summary-handler.md) for the plugin.

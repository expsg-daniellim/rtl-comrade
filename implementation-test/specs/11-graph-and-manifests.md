# Spec 11: Graph YAML and manifest registration

**Depends on:** specs 02–10 (all contracts + modules).
**References:** [06 — `graphs/test.yaml`](../06-graph-yaml.md).

## Before you start

Read the harness config-file docs this spec assembles: `docs/harness_configs/graph.md` (nodes, edges, node/CLI edge sources, and the **"Contract port mappings"** section the `results-summary` node uses to declare its 13-port fan-in surface), `docs/harness_configs/plugin_manifest.md` (the module/contract `config.yaml` shape), and `docs/harness_configs/rtl_comrade_config.md` (registering the `test` subcommand). `docs/harness/validation.md` explains the static checks the acceptance criteria rely on (cycles, overloaded inputs, and how a `contract_port_mappings` node is screened against its declared contract-port surface). **[`06 — graphs/test.yaml`](../06-graph-yaml.md) is the wiring authority** — its `graphs/test.yaml` (nodes/contracts + edge list) carries the split-edge model and the `results-summary` fan-in. This spec is the sole owner of `graphs/test.yaml`, `modules/config.yaml`, `contracts/config.yaml`, and the `rtl_comrade_config.yaml` entry — no sibling specs append to those files.

## Goal

Assemble the test graph YAML, finalise plugin manifests, and register the `test` subcommand in `rtl_comrade_config.yaml`.

## Deliverables

- **`graphs/test.yaml`** — per the wiring authority [`06 — graphs/test.yaml`](../06-graph-yaml.md) (the split-edge nodes/contracts + edge list): all nodes (including the `git-status` setup node and the `results-summary` sink), CLI edges (including `test_name` as positional with `option: false, default: ""`), the setup chain, persistent-config fan-out (config singletons feed `keyed_join`/`default` nodes via `persistent_inputs`), list-mode routing, and the **split per-test/per-run edges** (`test`/`model`/`simv`/`run_id`/`seed`/`filelist`/`command`/`timeout`/`proc`/`randseed`/`randseed_done`) wired through the `keyed_join` command-builders and the two parallel post-sim branches (side-effects ∥ classification); and the **13 terminal result ports wired to `results-summary`** (the `any` contract fanning them in, surface declared via `contract_port_mappings`). There is **no** `logging` block.
- **`modules/rtl_buddy/summarise_results.py`** — the `SummariseResultsMod` in-graph results-summary sink (spec [10d](10d-summarise-results.md)), a config-less module reached by the manifest. (`graphs/log/summary.py`'s `SummaryProcessor` (spec [10c](10c-summary-handler.md)) is **dormant** — kept but not wired into `test`'s logging.)
- **`modules/config.yaml`** — full manifest covering every module from specs 03–10 (`run-process`, the setup chain incl. `git-status`, selection/expansion, prep, compile cycle, sim cycle, post, control). The four file blocks each child spec contributes to (verbatim from [06](../06-graph-yaml.md)):
  ```yaml
  - file: rtl_buddy/setup.py
    plugins:
    - { name: discover-config-file, class_name: DiscoverConfigFileMod }
    - { name: prepend-cwd-path,     class_name: PrependCwdPathMod }
    - { name: parse-root-config,    class_name: ParseRootConfigMod }
    - { name: select-platform,      class_name: SelectPlatformMod }
    - { name: resolve-builder,      class_name: ResolveBuilderMod }
    - { name: work-dir,             class_name: WorkDirMod }
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
  - file: rtl_buddy/summarise_results.py
    plugins:
    - { name: summarise-results, class_name: SummariseResultsMod }
  ```
- **`contracts/config.yaml`** — the `any` registration from spec 02 (wired into `test` on the `results-summary` node, and reusable elsewhere). Parallel safety comes from per-tag artefact naming — see [06](../06-graph-yaml.md) and [05 — Interim CWD-collision posture](../05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
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

Graph-assembly checks in `tests/test_graph_assembly.py` (or similar) — the inputs are the committed YAML files, the expected outputs are load/validation outcomes. Fixtures: the harness `Graph.from_file` / `validation.py` API; a CLI runner (subprocess or the harness's test runner) for the `--help` cases.

- `Graph.from_file("graphs/test.yaml")` → loads without error; every node `class_name` resolves against `modules/config.yaml` (incl. `summarise-results`) and every contract against `contracts/config.yaml` (incl. `any`) (boundary: no dangling manifest reference).
- `validation.py` on the loaded graph → reports **no** cycles and **no** overloaded inputs (single-source-per-port holds). The `results-summary` node's `contract_port_mappings` builds its 13-port surface; all 13 terminal edges validate as destinations against that surface (boundary: a `contract_port_mappings` node screened against its declared contract ports, not the `**?**` module signature).
- Running the graph → the 13 terminal `TestResult`s fan into `results-summary` via the `any` contract; its `finalise()` renders the table once at run end (no-op on an empty/list-mode run). No result port logs `no_destination` (all are wired).
- `uv run rtl-comrade --help` → output lists `test` with the help string `"Compile and simulate a SystemVerilog/UVM test suite."`.
- `uv run rtl-comrade test --help` → output lists every CLI edge (`test_config`, `logs_dir` type `str` default `"logs"`, `builder`, `test_name` positional with `option: false, default: ""`, `list`, `rnd_new`, `rnd_last`, `builder_mode`, `early_stop`) with the types/defaults from [06](../06-graph-yaml.md).

## Acceptance criteria

- `uv run rtl-comrade --help` lists `test` with the help string.
- `uv run rtl-comrade test --help` lists every CLI edge from [06](../06-graph-yaml.md) (`test_config`, `logs_dir` type `str` default `"logs"`, `builder`, `test_name` positional, `list`, `rnd_new`, `rnd_last`, `builder_mode`, `early_stop`) with correct types/defaults.
- Graph loads without validation errors — `Graph.from_file("graphs/test.yaml")` succeeds.
- `validation.py` reports no cycles or overloaded inputs.
- Every module name registered in `modules/config.yaml` and every contract name in `contracts/config.yaml` resolves to its declared class (this spec is the central owner of the registry-resolvability assertion the module specs 03–10 reference).

## Constraints

- Wire per [`06 — graphs/test.yaml`](../06-graph-yaml.md), the wiring authority (its `graphs/test.yaml` carries the split-edge model and the `results-summary` fan-in). Reconcile **toward the built module signatures** (specs 03–10 as converted to the split).
- The 13 result ports are **wired** to `results-summary` (one edge each → a distinct contract port declared in the node's `contract_port_mappings`, each → `[result]`); the `any` contract delivers each `TestResult` under `result`.
- Register the `any` contract and wire it on the `results-summary` node (`contract_config: { mapping: result }`); it stays reusable by other graphs.
- The summary is an **in-graph module** (`summarise-results` → `SummariseResultsMod`, a manifest entry); `test.yaml` has **no** `logging` block. The dormant `SummaryProcessor` ([10c](10c-summary-handler.md)) is not wired.
- The assembled graph must load with no cycles and no overloaded inputs (single-source-per-port).

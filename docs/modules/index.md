# `rtl_buddy` `test`-flow Modules

Reference for the modules ported into `modules/rtl_buddy/` to run the `test` graph (`graphs/test.yaml`). Each module is one node-local work unit: it reimplements a slice of upstream `rtl_buddy`'s single-test compile/run/report flow as a graph node.

One file per module, so an agent reading up on one module is never handed another's detail. Read the file for the module you are working on.

See also:

- [docs/module-implementation/implementation.md](../module-implementation/implementation.md) — how the harness turns a `run(...)` signature into ports, and the rules module authors follow
- [docs/module-implementation/testing.md](../module-implementation/testing.md) — testing modules in isolation
- [docs/contracts/index.md](../contracts/index.md) — the scheduling policies these nodes are paired with
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML that wires them together
- [doc-structure.md](doc-structure.md) — the per-module file format

These docs describe *what each module does* — its inputs, outputs, config, and failure routing. Scheduling (when a node runs, which inputs it waits for) is the contract's job, not the module's; the "Graph node" section on each page names the contract the `test` graph pairs it with, but the module itself is contract-agnostic.

## Modules by stage

The `test` flow is a linear pipeline that fans out per test (and per run). The stage groupings below are for navigation only — each module has its own file.

**Setup** (`setup.py`) — bootstrap config, platform, builder, directories, suite, seed mode

- [discover-config-file](discover-config-file.md) · [prepend-cwd-path](prepend-cwd-path.md) · [parse-root-config](parse-root-config.md) · [select-platform](select-platform.md) · [resolve-builder](resolve-builder.md) · [work-dir](work-dir.md) · [ensure-logs-dir](ensure-logs-dir.md) · [parse-suite-config](parse-suite-config.md) · [derive-seed-mode](derive-seed-mode.md) · [git-status](git-status.md)

**Selection & expansion** (`setup.py`) — route list-mode, select, filter, load model, sweep

- [route-list-mode](route-list-mode.md) · [list-test-names](list-test-names.md) · [select-tests](select-tests.md) · [filter-reglvl](filter-reglvl.md) · [load-model](load-model.md) · [expand-sweep](expand-sweep.md)

**Prep** (`build.py`) — preproc script, filelist generation

- [run-preproc](run-preproc.md) · [write-filelist](write-filelist.md)

**Subprocess runner** (`build.py`) — reusable, used by both compile and sim

- [run-process](run-process.md)

**Compile** (`build.py`) — build the compile command, interpret its result

- [build-compile-cmd](build-compile-cmd.md) · [interpret-compile](interpret-compile.md)

**Sim** (`sim.py`) — fan out runs, resolve seed, build/run sim, persist seed, symlink, interpret

- [expand-runs](expand-runs.md) · [resolve-seed](resolve-seed.md) · [build-sim-cmd](build-sim-cmd.md) · [write-randseed](write-randseed.md) · [link-latest](link-latest.md) · [interpret-sim](interpret-sim.md)

**Post** (`sim.py`) — route UVM vs plain, parse the log into a verdict

- [route-post](route-post.md) · [parse-log](parse-log.md) · [parse-uvm-log](parse-uvm-log.md)

**Early-stop control** (`control.py`)

- [early-stop-gate](early-stop-gate.md)

## Data flow at a glance

```
discover → parse-root → select-platform → resolve-builder ┐
work-dir → ensure-logs                                     │ (persistent config,
parse-suite → route-list ──list──▶ list-test-names         │  fanned to many nodes)
             └──run──▶ select ─test▶ filter ─test▶ load-model ─test/model▶ sweep
                                                                              │
  sweep ─test/model▶ preproc ▶ gate-pre ▶ filelist ─test/filelist▶ cc-build ─command▶ cc-run
                                                                              │
  cc-run ─proc▶ cc-int ▶ gate-comp ▶ expand-runs ▶ resolve-seed ▶ build-sim-cmd ─command▶ sim-run
                                                                              │
  sim-run ─proc▶ {write-randseed, link-latest, interpret-sim ▶ gate-sim ▶ route-post}
  route-post ──uvm──▶ parse-uvm-log
             └─plain─▶ parse-log
```

Every failure, skip, timeout, or early-stop emits a diagnostic log event (`log.error` or `log.info`). The `ConsoleSummaryProcessor` and `FileSummaryProcessor` logging plugins match these events by name, accumulate one row per test, and render the results table at end of run. See [docs/logger/summary-processor.md](../logger/summary-processor.md).

## Shared value types

The modules exchange a small set of frozen dataclasses from `modules/rtl_buddy/schema/`. `KeyedValue` is the exception: it belongs to the contract layer (`contracts/sentinels.py`), since [`keyed_join`](../contracts/keyed_join.md) both reads and constructs it, and the schema package re-exports it so the import path is unchanged. Most `keyed_join` nodes set `unwrap: true`, so the envelope rides the wire but never reaches module code — only [expand-sweep](expand-sweep.md) and [expand-runs](expand-runs.md), which mint new keys, construct it themselves.

| Type | Fields | Role |
|---|---|---|
| `KeyedValue[T]` | `key`, `value` | a value tagged with a test/run key, so `keyed_join` can correlate split edges |
| `Command` | `key`, `argv`, `stdout_path`, `stderr_path` | a subprocess to launch (compile or sim), consumed by `run-process` |
| `Proc` | `key`, `rc`, `stdout_path`, `stderr_path` | a finished subprocess; `rc is None` means it was killed on timeout |
| `RandSeed` / `RandSeedDone` | seed + paths / `key` | the resolved seed to persist, and an ordering token so `link-latest` runs after the seed is written |
| `SeedMode` | enum | `NEW` (fresh random), `REPLAY` (reuse last), `DEFAULT` (builder-configured) |
| `RunDepth` | enum | ordered phases `pre` < `comp` < `sim` < `post`; drives `early-stop-gate` |

## Results reporting

The results summary is not an in-graph node — it is handled by the `ConsoleSummaryProcessor` and `FileSummaryProcessor` logging plugins (`graphs/log/summary.py`), wired in the `test` graph's `logging:` block. These match diagnostic log events by name (e.g. `compile_failed`, `parse_log_passed`, `test_skipped`, `test_stopped_early`), accumulate one row per test, and render the table at end of run. See [docs/logger/summary-processor.md](../logger/summary-processor.md).

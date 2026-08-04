# The `test` Graph

Graph file: `graphs/test.yaml` — registered as the `test` subcommand in `rtl_comrade_config.yaml`.

See also:

- [index.md](index.md) — graphs usage reference: CLI, output layout, hook extensions, and known issues
- [docs/modules/index.md](../modules/index.md) — module reference
- [docs/contracts/index.md](../contracts/index.md) — the scheduling policies the nodes are paired with
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML format (nodes, edges, CLI edges, contract config)
- [docs/running.md](../running.md) — invocation, options, config discovery, exit codes

The `test` graph is a native reimplementation of upstream `rtl_buddy`'s single-test compile/simulate/report flow as an `rtl-comrade` graph. It reads the project's config and test suite, then for each selected test compiles the design, runs the simulation, and classifies the outcome. It is a linear pipeline that **fans out** per test (and per run); every failure, skip, or early-stop emits a diagnostic log event that the summary logging plugins collect into a results table at end of run.

## Invocation

```bash
uv run rtl-comrade test [TEST_NAME] [options]
```

`TEST_NAME` is an optional positional argument; with no name, every test in the suite runs. For option defaults and effects — and the common options (`--builder`, `--builder-mode`, `--early-stop`) shared with the other commands — see [index.md § CLI reference](index.md#cli-reference). Within the graph the parameters feed:

| Parameter | Destination |
|---|---|
| `TEST_NAME` | [select-tests](../modules/select-tests.md) |
| `--test-config` / `-c` | [parse-suite-config](../modules/parse-suite-config.md) |
| `--logs-dir` | [ensure-logs-dir](../modules/ensure-logs-dir.md) |
| `--builder` / `-B` | [resolve-builder](../modules/resolve-builder.md) |
| `--builder-mode` / `-M` | [build-compile-cmd](../modules/build-compile-cmd.md), [build-sim-cmd](../modules/build-sim-cmd.md) |
| `--list` | `route-list` (`flag-gate` instance) |
| `--rnd-new` / `-n`, `--rnd-last` / `-l` | [derive-seed-mode](../modules/derive-seed-mode.md) |
| `--early-stop` / `-E` | the three [early-stop-gate](../modules/early-stop-gate.md) nodes |

## Config files read

The project inputs (`root_config.yaml`, `tests.yaml`, `models.yaml`) and their discovery are described in [index.md § Project inputs](index.md#project-inputs). In the `test` graph they are consumed by:

| File | Node |
|---|---|
| `root_config.yaml` | [discover-config-file](../modules/discover-config-file.md) → [parse-root-config](../modules/parse-root-config.md) |
| `tests.yaml` | [parse-suite-config](../modules/parse-suite-config.md) |
| `models.yaml` | [resolve-model-ref](../modules/resolve-model-ref.md) (path) → [load-model](../modules/load-model.md) (read) |

## Pipeline

For the full GitHub-rendered dataflow (per-edge payloads and pairing contracts), see [`test-dataflow-diagram.md`](test-dataflow-diagram.md). The same flow in brief:

```
discover → parse-root → select-platform → resolve-builder ┐
work-dir → ensure-logs                                     │ (persistent config,
parse-suite → route-list ──on──▶ list-test-names           │  fanned to many nodes)
             └──off──▶ select ─test▶ filter ─test▶ model-ref ─name/path▶ load-model ─model▶ sweep
                                                    └─test──────────────────────────────────────▶
                                                    └─test▶ load-model
                                                                              │
  sweep ─test/model▶ preproc ▶ gate-pre ─test/model▶ fl-model-ref → fl-model-root → fl-model ┐
                                  └─test▶ fl-tb ──────────────────────────────────────────────▶│
                                         fl-merge → fl-norm → fl-dedup → filelist             │
                                         fl-path ────────────────────────────▶│                │
                                                              filelist ─filelist▶ cc-build ─command▶ cc-run
                                                                              │
  cc-run ─proc▶ cc-int ▶ gate-comp ▶ expand-runs ▶ resolve-seed ▶ build-sim-cmd ─command▶ sim-run
                                                                              │
  sim-run ─proc▶ {write-randseed, link-latest, interpret-sim ▶ gate-sim ▶ route-post}
  route-post ──uvm──▶ parse-uvm-log
             └─plain─▶ parse-log
```

The flow reads in stages:

1. **Setup** — locate and parse `root_config.yaml`, pick the platform and builder from the host `uname`, resolve the working and logs directories, parse the suite, and derive the seed mode. These one-shot nodes produce the persistent configuration fanned out to the rest of the graph.
2. **List vs run** — `--list` short-circuits to [list-test-names](../modules/list-test-names.md) and prints nothing else; otherwise the suite enters the run pipeline.
3. **Selection & expansion** — select the requested tests, filter by register level, resolve the model reference, load each test's model, and expand sweep variants. From here the main line carries **split edges** (see below).
4. **Prep** — run the optional preproc script, then generate the compile filelist.
5. **Compile** — build the compile command, run it via [run-process](../modules/run-process.md), interpret the return code.
6. **Sim** — fan out into runs, resolve the seed, build and run the sim command (again via [run-process](../modules/run-process.md)), persist the seed, refresh the `latest` symlinks, and interpret the outcome.
7. **Post** — route UVM vs plain tests to the matching log parser, which classifies the outcome as PASS or FAIL via a diagnostic log event.

## Modules by stage

Quick reference for the modules at each stage, with links to their doc pages. See [docs/modules/index.md](../modules/index.md) for the full module catalog.

**Setup** (`setup.py`) — bootstrap config, platform, builder, directories, suite, seed mode

- [discover-config-file](../modules/discover-config-file.md) · [prepend-cwd-path](../modules/prepend-cwd-path.md) · [parse-root-config](../modules/parse-root-config.md) · [select-platform](../modules/select-platform.md) · [resolve-builder](../modules/resolve-builder.md) · [work-dir](../modules/work-dir.md) · [ensure-logs-dir](../modules/ensure-logs-dir.md) · [parse-suite-config](../modules/parse-suite-config.md) · [derive-seed-mode](../modules/derive-seed-mode.md) · [git-status](../modules/git-status.md)

**List mode** (`control.py`) — route `--list` flag to list-names or run

- `route-list` (`flag-gate` instance) · [list-test-names](../modules/list-test-names.md)

**Selection & expansion** (`setup.py`) — select, filter, load model, sweep

- [select-tests](../modules/select-tests.md) · [filter-reglvl](../modules/filter-reglvl.md) · [resolve-model-ref](../modules/resolve-model-ref.md) · [load-model](../modules/load-model.md) · [expand-sweep](../modules/expand-sweep.md)

**Prep** (`build.py`) — preproc script, filelist pipeline

- [run-preproc](../modules/run-preproc.md) · filelist-extract · filelist-normalise · filelist-dedup · prioritised-merge · filelist-path · [write-filelist](../modules/write-filelist.md)

**Subprocess runner** (`build.py`) — reusable, used by both compile and sim

- [run-process](../modules/run-process.md)

**Compile** (`build.py`) — build the compile command, interpret its result

- [build-compile-cmd](../modules/build-compile-cmd.md) · [interpret-compile](../modules/interpret-compile.md)

**Sim** (`sim.py`) — fan out runs, resolve seed, build/run sim, persist seed, symlink, interpret

- [expand-runs](../modules/expand-runs.md) · [resolve-seed](../modules/resolve-seed.md) · [build-sim-cmd](../modules/build-sim-cmd.md) · [write-randseed](../modules/write-randseed.md) · [link-latest](../modules/link-latest.md) · [interpret-sim](../modules/interpret-sim.md)

**Post** (`sim.py`) — route UVM vs plain, parse the log into a verdict

- [route-post](../modules/route-post.md) · [parse-log](../modules/parse-log.md) · [parse-uvm-log](../modules/parse-uvm-log.md)

**Control** (`control.py`)

- [early-stop-gate](../modules/early-stop-gate.md) · `flag-gate`

## Shared value types

The modules exchange a small set of frozen dataclasses from `modules/rtl_buddy/schema/`. `KeyedValue` is the exception: it belongs to the contract layer (`contracts/sentinels.py`), since [`keyed_join`](../contracts/keyed_join.md) both reads and constructs it, and the schema package re-exports it so the import path is unchanged. Most `keyed_join` nodes set `unwrap: true`, so the envelope rides the wire but never reaches module code — only [expand-sweep](../modules/expand-sweep.md), [expand-runs](../modules/expand-runs.md), and [resolve-model-ref](../modules/resolve-model-ref.md), which mint or project keys, construct it themselves.

| Type | Fields | Role |
|---|---|---|
| `KeyedValue[T]` | `key`, `value` | a value tagged with a test/run key, so `keyed_join` can correlate split edges |
| `Command` | `key`, `argv`, `stdout_path`, `stderr_path` | a subprocess to launch (compile or sim), consumed by `run-process` |
| `Proc` | `key`, `rc`, `stdout_path`, `stderr_path` | a finished subprocess; `rc is None` means it was killed on timeout |
| `RandSeed` / `RandSeedDone` | seed + paths / `key` | the resolved seed to persist, and an ordering token so `link-latest` runs after the seed is written |
| `SeedMode` | enum | `NEW` (fresh random), `REPLAY` (reuse last), `DEFAULT` (builder-configured) |
| `RunDepth` | enum | ordered phases `pre` < `comp` < `sim` < `post`; drives `early-stop-gate` |

## Contracts and the keyed model

The graph relies on a few contract choices to coordinate the fan-out (full detail in [docs/contracts/index.md](../contracts/index.md)):

- **[`unit`](../contracts/unit.md)** — the one-shot setup nodes that must run exactly once (`parse-root`, `select-platform`, `resolve-builder`, `ensure-logs`, `parse-suite`, `seed-mode`, `route-list`).
- **[`default`](../contracts/default.md)** — source nodes and the fan-out points (`select`, `filter`, `model-ref`, `fl-model-ref`), the `unroll` constant, and the compile `run-process`.
- **[`keyed_join`](../contracts/keyed_join.md)** — the backbone of the per-test/per-run stages and the filelist pipeline. Because a single test travels as **split edges** (e.g. a `test` payload alongside a keyed `model` or `filelist` payload), each downstream node uses `keyed_join` with `key_field: key` to reassemble the payloads belonging to the same test before invoking the module. [load-model](../modules/load-model.md) uses `keyed_join` with `unwrap: true` to receive the model name and path as bare values and rewrap its output. The filelist pipeline nodes (`fl-model-root`, `fl-model`, `fl-tb`, `fl-merge`, `fl-norm`, `fl-dedup`, `fl-path`, `filelist`) all use `keyed_join` with `unwrap: true`, running their envelope-agnostic modules once per test. [expand-runs](../modules/expand-runs.md) re-keys each item to `<test.key>#<run_id>` so per-run stages stay correlated. Most of those nodes also set `unwrap: true`: the `KeyedValue` envelope stays on the wire, but the contract strips it before the module sees it and re-attaches the assembled key to what the module emits, so only the fan-out modules that mint new keys ([expand-sweep](../modules/expand-sweep.md) and `expand-runs`) and [resolve-model-ref](../modules/resolve-model-ref.md) (plus `fl-model-ref`), which project keys, construct `KeyedValue` themselves.

Persistent configuration (builder config, work dir, logs dir, seed mode, root config) is wired as `persistent_inputs` on the joining contracts, so one upstream value is cached and reused for every keyed item without re-delivery.

## Results and failure routing

Every off-ramp emits a diagnostic log event that the summary logging plugins match by name. A test that is skipped by register level, fails to prep, times out, is stopped early, or completes and is parsed all land exactly one row in the final table. See each module's *Failure routing* section for how it decides between an abort (`log.fatal`), a deferred failure (`log.error`), and a quiet skip/stop (`log.info`).

The `ConsoleSummaryProcessor` and `FileSummaryProcessor` logging plugins (`graphs/log/summary.py`) are wired in the graph's `logging:` block. They accumulate rows from matched events and render the results table at end of run. See [docs/logger/summary-processor.md](../logger/summary-processor.md).

## Outputs

The graph's compile/sim logs, seeds, generated filelist, summary log, and the `test.*` latest-run symlinks are described in [index.md § Logging & output layout](index.md#logging--output-layout). The colourised summary table is printed to the console by `ConsoleSummaryProcessor`.

**Exit code** — a `log.error` from any module sets `handler.failure = True`, making the run exit non-zero (deferred until the whole suite finishes); a `log.fatal` in any setup node exits immediately. See [docs/running.md](../running.md) for exit-code semantics.

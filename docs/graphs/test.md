# The `test` Graph

Graph file: `graphs/test.yaml` — registered as the `test` subcommand in `rtl_comrade_config.yaml`.

See also:

- [index.md](index.md) — graphs usage reference: CLI, output layout, hook extensions, and known issues
- [docs/modules/index.md](../modules/index.md) — reference for every node module in this graph
- [docs/contracts/index.md](../contracts/index.md) — the scheduling policies the nodes are paired with
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML format (nodes, edges, CLI edges, contract config)
- [docs/running.md](../running.md) — invocation, options, config discovery, exit codes

The `test` graph is a native reimplementation of upstream `rtl_buddy`'s single-test compile/simulate/report flow as an `rtl-comrade` graph. It reads the project's config and test suite, then for each selected test compiles the design, runs the simulation, classifies the outcome, and prints a results summary. It is a linear pipeline that **fans out** per test (and per run) and **fans in** to one summary node, with every failure or short-circuit routed to that same summary so no test disappears silently.

## Invocation

```bash
uv run rtl-comrade test [TEST_NAME] [options]
```

`TEST_NAME` is an optional positional argument; with no name, every test in the suite runs. For option defaults and effects — and the common options (`--builder`, `--builder-mode`, `--early-stop`) shared with the other commands — see [index.md § CLI reference](index.md#cli-reference). Within the graph the parameters feed:

| Parameter | Destination |
|---|---|
| `TEST_NAME` | [select-tests](../modules/select-tests.md) |
| `--test-config` | [parse-suite-config](../modules/parse-suite-config.md) |
| `--logs-dir` | [ensure-logs-dir](../modules/ensure-logs-dir.md) |
| `--builder` | [resolve-builder](../modules/resolve-builder.md) |
| `--builder-mode` | [build-compile-cmd](../modules/build-compile-cmd.md), [build-sim-cmd](../modules/build-sim-cmd.md) |
| `--list` | [route-list-mode](../modules/route-list-mode.md) |
| `--rnd-new` / `--rnd-last` | [derive-seed-mode](../modules/derive-seed-mode.md) |
| `--early-stop` | the three [early-stop-gate](../modules/early-stop-gate.md) nodes |

## Config files read

The project inputs (`root_config.yaml`, `tests.yaml`, `models.yaml`) and their discovery are described in [index.md § Project inputs](index.md#project-inputs). In the `test` graph they are consumed by:

| File | Node |
|---|---|
| `root_config.yaml` | [discover-config-file](../modules/discover-config-file.md) → [parse-root-config](../modules/parse-root-config.md) |
| `tests.yaml` | [parse-suite-config](../modules/parse-suite-config.md) |
| `models.yaml` | [load-model](../modules/load-model.md) |

## Pipeline

For the full GitHub-rendered dataflow (per-edge payloads and pairing contracts), see [`test-dataflow-diagram.md`](test-dataflow-diagram.md). The same flow in brief:

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
  route-post ──uvm──▶ parse-uvm-log ┐
             └─plain─▶ parse-log ───┼─▶ results-summary ─table▶ {print-summary, write-summary-log}
  (every skip / fail / timeout / early-stop port also fans into results-summary)
```

The flow reads in stages (see [docs/modules/index.md](../modules/index.md) for the per-module reference):

1. **Setup** — locate and parse `root_config.yaml`, pick the platform and builder from the host `uname`, resolve the working and logs directories, parse the suite, and derive the seed mode. These one-shot nodes produce the persistent configuration fanned out to the rest of the graph.
2. **List vs run** — `--list` short-circuits to [list-test-names](../modules/list-test-names.md) and prints nothing else; otherwise the suite enters the run pipeline.
3. **Selection & expansion** — select the requested tests, filter by register level, load each test's model, and expand sweep variants. From here the main line carries **split edges** (see below).
4. **Prep** — run the optional preproc script, then generate the compile filelist.
5. **Compile** — build the compile command, run it via [run-process](../modules/run-process.md), interpret the return code.
6. **Sim** — fan out into runs, resolve the seed, build and run the sim command (again via [run-process](../modules/run-process.md)), persist the seed, refresh the `latest` symlinks, and interpret the outcome.
7. **Post** — route UVM vs plain tests to the matching log parser, producing a verdict `TestResult`.
8. **Summary** — [summarise-results](../modules/summarise-results.md) accumulates every result and renders the table, fanned to a console sink and a log-file sink.

## Contracts and the keyed model

The graph relies on a few contract choices to coordinate the fan-out (full detail in [docs/contracts/index.md](../contracts/index.md)):

- **[`unit`](../contracts/unit.md)** — the one-shot setup nodes that must run exactly once (`parse-root`, `select-platform`, `resolve-builder`, `ensure-logs`, `parse-suite`, `seed-mode`, `route-list`).
- **[`default`](../contracts/default.md)** — source nodes and the fan-out points (`select`, `filter`, `load-model`), plus the compile `run-process` and the two summary sinks.
- **[`keyed_join`](../contracts/keyed_join.md)** — the backbone of the per-test/per-run stages. Because a single test travels as **split edges** (e.g. a `test` payload alongside a keyed `model` or `filelist` payload), each downstream node uses `keyed_join` with `key_field: key` to reassemble the payloads belonging to the same test before invoking the module. [expand-runs](../modules/expand-runs.md) re-keys each item to `<test.key>#<run_id>` so per-run stages stay correlated.
- **[`any`](../contracts/any.md)** — `results-summary` uses `any` to fan the 13 terminal result ports into its single `result` input, one at a time, accumulating rows until all streams end.

Persistent configuration (builder config, work dir, logs dir, seed mode, root config) is wired as `persistent_inputs` on the joining contracts, so one upstream value is cached and reused for every keyed item without re-delivery.

## Results and failure routing

Every off-ramp emits a `TestResult` on a dedicated port, and all 13 fan into `results-summary`:

`compile_fail`, `sim_timeout`, `load_model`, `filelist`, `sweep`, `preproc`, `seed`, `parse_plain`, `parse_uvm`, `skip`, `stop_pre`, `stop_comp`, `stop_sim`.

So a test that is skipped by register level, fails to prep, times out, is stopped early, or completes and is parsed all land exactly one row in the final table. See each module's *Failure routing* section for how it decides between an abort (`log.fatal`), a deferred failure (`log.error`), and a routed `fail`/`skip` result.

## Outputs

The graph's compile/sim logs, seeds, generated filelist, summary log, and the `test.*` latest-run symlinks are described in [index.md § Logging & output layout](index.md#logging--output-layout). The colourised summary table is printed to the console by [print-summary](../modules/print-summary.md).

**Exit code** — when any result is a `FAIL`, [summarise-results](../modules/summarise-results.md) logs a consolidated `ERROR`, which makes the run exit non-zero (deferred until the whole suite finishes); a `log.fatal` in any setup node exits immediately. See [docs/running.md](../running.md) for exit-code semantics.

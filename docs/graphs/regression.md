# The `regression` Graph

Graph file: `graphs/regression.yaml` — registered as the `regression` subcommand in `rtl_comrade_config.yaml`.

See also:

- [test.md](test.md) — the `test` graph this one is derived from; everything not listed here is described there
- [regression-dataflow-diagram.md](regression-dataflow-diagram.md) — the full dataflow, with the delta from `test` highlighted
- [index.md](index.md) — graphs usage reference: CLI, output layout, hook extensions, and known issues
- [docs/modules/index.md](../modules/index.md) — module reference
- [docs/logger/regression-summary-processor.md](../logger/regression-summary-processor.md) — the regression summary table processors
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML format (nodes, edges, CLI edges, contract config)
- [docs/running.md](../running.md) — invocation, options, config discovery, exit codes

The `regression` graph is a native reimplementation of upstream `rtl_buddy`'s `regression` command (`do_rtl_regression`): it reads a regression config listing several suite configs and runs every test in every suite whose register level falls in the requested range. It is `test.yaml` with six changes; every other node, edge, and contract is identical:

1. **Suite stream.** `resolve-reg-path` ([resolve-reg-config-path](../modules/resolve-reg-config-path.md)) resolves the regression config from `--reg-config` or, when that is empty, from `root_config.yaml`'s `reg-cfg-path` (relative to `root_config.yaml`'s directory). `parse-reg` ([parse-reg-config](../modules/parse-reg-config.md)) streams one suite config path per entry into `parse-suite`, which runs under the [`default`](../contracts/default.md) contract (not `unit`) so it fires once per suite. The `parse-reg → parse-suite` edge is `required: true`, so `parse-suite` awaits the stream rather than firing on its own `tests.yaml` default.
2. **Per-suite directories.** `work-dir` and `ensure-logs` are absent. Two [extract-suite-dir](../modules/extract-suite-dir.md) instances emit each test's suite directory (`base_dir`, wired to both the `base_dir` and `work_dir` ports) and its created `logs/` directory as keyed values: `extract-dir` after `gate-pre` serves the pre-fan-out nodes (`fl-tb`, `fl-norm`, `fl-path`, `cc-build`, `cc-run`), and `extract-dir-post` after `runs` serves the post-fan-out nodes (`seed`, `sim-build`, `sim-run`, `randseed`, `link-latest`), whose keys carry the `#<run_id>` suffix [expand-runs](../modules/expand-runs.md) adds. Those ports move from `persistent_inputs` to keyed inputs; `cc-run` switches to [`keyed_join`](../contracts/keyed_join.md) (with `timeout` persistent, since compile has no timeout source) and `randseed` / `link-latest` gain `unwrap: true`.
3. **Suite-key prefixing.** `parse-suite` sets `prefix_suite: true`, so each test key becomes `<suite>/<test>`, keeping same-named tests in different suites distinct.
4. **Fixed seed mode.** The `seed-mode` node ([derive-seed-mode](../modules/derive-seed-mode.md)) and `--rnd-new` / `--rnd-last` are replaced by `const-seed-mode`, a `constant` emitting `SeedMode.DEFAULT` to [resolve-seed](../modules/resolve-seed.md).
5. **No list mode or test name.** The `route-list` / `list-names` nodes and the `--list`, `TEST_NAME`, and `--test-config` parameters are absent; `parse-suite` feeds `select` directly and every test in each suite is selected.
6. **Regression summary.** The `logging:` block names `FileRegressionSummaryProcessor` and `ConsoleRegressionSummaryProcessor` (`graphs/log/regression_summary.py`) in place of the `test` summary processors, rendering rtl_buddy's regression table. Three `logger` nodes emit the metadata it needs as info events: `log-builder` (`regression_builder`, the builder `name` from `resolve-builder`), `log-builder-mode` (`regression_builder_mode`, the `--builder-mode` value), and `log-suite` (`regression_suite`, each suite's leaf directory name and config `path` from `parse-suite`). See [regression-summary-processor.md](../logger/regression-summary-processor.md).

## Invocation

```bash
uv run rtl-comrade regression [options]
```

For option defaults and effects see [index.md § CLI reference](index.md#cli-reference). Within the graph the parameters feed:

| Parameter | Destination |
|---|---|
| `--reg-config` / `-c` | [resolve-reg-config-path](../modules/resolve-reg-config-path.md) |
| `--reg-level` / `-l`, `--start-level` / `-s` | [filter-reglvl](../modules/filter-reglvl.md) |
| `--logs-dir` / `-L` | the two [extract-suite-dir](../modules/extract-suite-dir.md) nodes |
| `--builder` / `-B` | [resolve-builder](../modules/resolve-builder.md) |
| `--builder-mode` / `-M` | [build-compile-cmd](../modules/build-compile-cmd.md), [build-sim-cmd](../modules/build-sim-cmd.md), `log-builder-mode` |
| `--early-stop` / `-E` | the three [early-stop-gate](../modules/early-stop-gate.md) nodes |

## Pipeline

The pipeline is the `test` pipeline ([test.md § Pipeline](test.md#pipeline)) with the setup and list stages changed:

```
resolve-reg-path ─path▶ parse-reg ─test_config (one per suite)▶ parse-suite ─suite_cfg▶ select ─test▶ filter ▶ …
gate-pre ─test▶ extract-dir      ─base_dir/logs_dir (keyed)▶ fl-tb, fl-norm, fl-path, cc-build, cc-run
runs     ─test▶ extract-dir-post ─base_dir/logs_dir (keyed)▶ seed, sim-build, sim-run, randseed, link-latest
const-seed-mode ─seed_mode▶ resolve-seed                                                   (persistent config)
resolve-builder ─builder_cfg▶ log-builder                                                  (summary metadata)
parse-suite     ─suite_cfg▶ log-suite                                                      (summary metadata)
```

`filter` receives `reg_level` and `start_level` from the CLI (both default `0`), so by default only level-0 tests run; tests outside the range are skipped with a `test_skipped` event and a `SKIP` summary row.

## Outputs

Outputs follow [index.md § Logging & output layout](index.md#logging--output-layout), except that each suite's outputs land in that suite's own directory rather than the working directory: `logs/` (or `--logs-dir`) is created under each suite directory, and the generated filelists, `test.*` symlinks, and the compile/sim subprocesses' working directory are the suite directory. The summary table follows rtl_buddy's regression layout: a `Builder: <builder>, Builder Mode: <mode>` line, then one row per test grouped under its suite config path ([regression-summary-processor.md](../logger/regression-summary-processor.md)).

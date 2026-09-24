# The `randtest` Graph

Graph file: `graphs/randtest.yaml` — registered as the `randtest` subcommand in `rtl_comrade_config.yaml`.

See also:

- [test.md](test.md) — the `test` graph this one is derived from; everything not listed here is described there
- [randtest-dataflow-diagram.md](randtest-dataflow-diagram.md) — the full dataflow, with the delta from `test` highlighted
- [index.md](index.md) — graphs usage reference: CLI, output layout, hook extensions, and known issues
- [docs/modules/index.md](../modules/index.md) — module reference
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML format (nodes, edges, CLI edges, contract config)
- [docs/running.md](../running.md) — invocation, options, config discovery, exit codes

The `randtest` graph is a native reimplementation of upstream `rtl_buddy`'s `randtest` command (`do_rand_test`): it runs one test several times, each with a fresh random seed, or replays the seed of one earlier run. It is `test.yaml` with three changes; every other node, edge, contract, and the `logging:` block is identical:

1. **Seed derivation.** The `seed-mode` node ([derive-seed-mode](../modules/derive-seed-mode.md), fed by `--rnd-new` / `--rnd-last`) is replaced by `derive-runs` ([derive-randtest-runs](../modules/derive-randtest-runs.md)), which collapses `RND_CNT` / `--rnd-rpt` into the `run_ids` list for [expand-runs](../modules/expand-runs.md) and the `seed_mode` for [resolve-seed](../modules/resolve-seed.md).
2. **No list mode.** The `route-list` (`flag-gate`) and `list-names` ([list-test-names](../modules/list-test-names.md)) nodes and the `--list` option are absent; `parse-suite` feeds `select` directly.
3. **Required test name.** `TEST_NAME` has no default, so it is a required positional argument.

## Invocation

```bash
uv run rtl-comrade randtest TEST_NAME [RND_CNT] [options]
```

For option defaults and effects see [index.md § CLI reference](index.md#cli-reference). Within the graph the parameters feed:

| Parameter | Destination |
|---|---|
| `TEST_NAME` | [select-tests](../modules/select-tests.md) |
| `RND_CNT` | [derive-randtest-runs](../modules/derive-randtest-runs.md) |
| `--rnd-rpt` / `-r` | [derive-randtest-runs](../modules/derive-randtest-runs.md) |
| `--test-config` / `-c` | [parse-suite-config](../modules/parse-suite-config.md) |
| `--logs-dir` | [ensure-logs-dir](../modules/ensure-logs-dir.md) |
| `--builder` / `-B` | [resolve-builder](../modules/resolve-builder.md) |
| `--builder-mode` / `-M` | [build-compile-cmd](../modules/build-compile-cmd.md), [build-sim-cmd](../modules/build-sim-cmd.md) |
| `--early-stop` / `-E` | the three [early-stop-gate](../modules/early-stop-gate.md) nodes |

## Pipeline

The pipeline is the `test` pipeline ([test.md § Pipeline](test.md#pipeline)) with the setup and list stages changed:

```
parse-suite ─suite_cfg▶ select ─test▶ filter ▶ …                    (no route-list / list-test-names)
derive-runs ─run_ids▶ expand-runs      ─seed_mode▶ resolve-seed      (persistent config)
```

`derive-runs` runs once under the [`unit`](../contracts/unit.md) contract. Its `run_ids` and `seed_mode` outputs land on the `persistent_inputs` that `runs` and `seed` already declare in `test.yaml`, so each compiled test fans out into one sim per run id:

- **New seeds** (`--rnd-rpt` negative, the default): run ids `1`..`RND_CNT`, each with a fresh random seed.
- **Replay** (`--rnd-rpt N`, `N >= 0`): the single run id `N`, reusing the seed recorded in `logs/<test>_NNNN.randseed`.

## Outputs

Outputs follow [index.md § Logging & output layout](index.md#logging--output-layout). Because every run carries a run id, the sim and seed filenames always carry the zero-padded run suffix (`logs/<test>_0001.log`, `.err`, `.randseed`, …); the compile log keeps the unsuffixed `logs/<test>.compile.log`. The `test.*` symlinks point at the newest run's outputs. The summary table has one row per run, each under the test name.

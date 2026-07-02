# Graphs

Each graph is an executable dependency graph the harness runs as a subcommand (registered in `rtl_comrade_config.yaml`). This page is the usage reference for the `rtl_buddy`-derived flows — the CLI, the on-disk output layout, the hook-script extensions, and known domain issues. For the internal wiring of a graph (nodes, edges, contracts, dataflow) see its own page.

See also:

- [test.md](test.md) — the `test` graph's pipeline, contracts, and per-node wiring
- [docs/modules/index.md](../modules/index.md) — reference for every node module
- [docs/running.md](../running.md) — global options, config discovery, exit codes
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the graph YAML format

## Available graphs

| Graph | Command | Page | Summary |
|---|---|---|---|
| `test` | `rtl-comrade test` | [test.md](test.md) | Compile and simulate a SystemVerilog/UVM test suite |

Upstream `rtl_buddy` also shipped `randtest`, `regression`, and `filelist` subcommands. Those are **not ported** — only the `test` flow is implemented here (see the port specs). Their upstream-only options (`--reg-config`, `--reg-level`, `--start-level`, `--rnd-rpt`, the `filelist` transforms) therefore do not exist in `rtl-comrade`.

## CLI reference

Global options (`--level`, `--config-file`) apply to every command and must appear before the subcommand — see [docs/running.md](../running.md).

### Common options

Shared by the test-running commands (`test` today; the future `randtest` / `regression`):

| Option | Default | Effect |
|---|---|---|
| `--builder` | platform default | override the builder from `root_config.yaml` |
| `--builder-mode` | `debug` | select the compile/run option set |
| `--early-stop` | `post` | stop each test at `pre`, `comp`, `sim`, or `post` |

### `test`

```bash
uv run rtl-comrade test [TEST_NAME] [options]
```

`TEST_NAME` is optional; with no name, every test in the suite runs. Accepts the common options above, plus:

| Option / argument | Default | Effect |
|---|---|---|
| `TEST_NAME` (positional) | all tests | run only the named test |
| `--test-config` | `tests.yaml` | suite file to read |
| `--logs-dir` | `logs` | output subdirectory for logs and seeds |
| `--list` | off | print the suite's test names and exit without running |
| `--rnd-new` | off | use a freshly generated seed instead of the configured one |
| `--rnd-last` | off | replay the seed from the previous `--rnd-new` run |

For which node each option feeds, see [test.md § Invocation](test.md#invocation).

## Project inputs

The commands read a small set of project YAML files, discovered relative to the working directory. These are shared across the `rtl_buddy`-derived commands.

| File | Contents |
|---|---|
| `root_config.yaml` | platforms, builders, and the RTL register field; discovered by ascending from the working directory to the git/filesystem root |
| `tests.yaml` | testbenches and per-test config (the suite) |
| `models.yaml` | the RTL model filelist for a design |

`root_config.yaml` is located first (via [discover-config-file](../modules/discover-config-file.md)); the suite and model paths are resolved relative to it.

## Logging & output layout

The `test` graph writes into the working directory and the logs subdirectory (`logs/` by default, or `--logs-dir`, created by [ensure-logs-dir](../modules/ensure-logs-dir.md)):

| Path | Written by | Contents |
|---|---|---|
| `logs/<test>.compile.log` / `.compile.err` | [build-compile-cmd](../modules/build-compile-cmd.md) + [run-process](../modules/run-process.md) | compile stdout / stderr |
| `logs/<test>.log` / `.err` | [build-sim-cmd](../modules/build-sim-cmd.md) + [run-process](../modules/run-process.md) | simulation stdout / stderr |
| `logs/<test>.randseed` | [write-randseed](../modules/write-randseed.md) | the seed used, for `--rnd-last` replay |
| `run.<test>.f` (working dir) | [write-filelist](../modules/write-filelist.md) | the generated compile filelist |
| `rtl_buddy.log` (working dir) | [write-summary-log](../modules/write-summary-log.md) | the plain-text results summary table |

When a test fans out into multiple runs, the sim/seed filenames gain a zero-padded `_NNNN` run suffix (e.g. `logs/<test>_0000.log`); with the single-run default the suffix is absent. Filenames are sanitised (non-alphanumeric characters become `_`).

For convenience, [link-latest](../modules/link-latest.md) maintains three symlinks in the working directory pointing at the newest run's outputs:

- `test.log` → `logs/<test>.log`
- `test.err` → `logs/<test>.err`
- `test.randseed` → `logs/<test>.randseed`

The colourised summary table is also printed to the console by [print-summary](../modules/print-summary.md).

## Extensions

A test may reference external Python hook scripts (paths in `tests.yaml`), executed in a namespace the graph provides. This mirrors upstream `rtl_buddy`'s hook mechanism.

### Sweep — expand one test into variants

If a test declares a `sweep` script, [expand-sweep](../modules/expand-sweep.md) executes it to expand that test into multiple keyed variants (e.g. one per plusarg combination). The script namespace:

- `logger` — the shared logger
- `TestConfig` — the class, for constructing variants
- `test_cfg` — the source `TestConfig` (its `model` field is temporarily the resolved model during execution)
- `root_cfg` — the `RootConfig`
- `out_test_cfgs` — the script appends the variant `TestConfig`s here

Variant keys are suffixed `#i`; `reglvl` is not meant to be mutated across variants.

### Preproc — mutate a test before compile

If a test declares a `preproc` script, [run-preproc](../modules/run-preproc.md) executes it before compilation, letting it mutate the test's plusdefines/plusargs. The namespace is `logger`, `test_cfg`, `root_cfg`.

### Postproc

Upstream `rtl_buddy` documents a postproc hook. In the ported `test` graph, post-processing is the **built-in log parse** — [parse-log](../modules/parse-log.md) for plain tests and [parse-uvm-log](../modules/parse-uvm-log.md) for UVM tests. A test's `postproc` path is parsed from `tests.yaml` but no node executes a postproc script; the custom postproc hook is not wired.

## Known issues

### Instance pRNG seeding

Random testing is not always reproducible under Verilator even with a fixed seed. VCS is recommended for stable random testing because of its hierarchical instance seeding: it seeds instantiated modules (and process threads, classes, etc.) from the instance name and its parents' names, so **name your instances** for stable seeding. [write-randseed](../modules/write-randseed.md) supports this by appending `HierInstanceSeed.txt` to the recorded `.randseed` when the sim used `hier_inst_seed`.

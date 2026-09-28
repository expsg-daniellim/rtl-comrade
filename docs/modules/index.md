# Modules

A module is node-local computation — the work a graph node does when its contract says it is time to run. Modules are contract-agnostic: they receive values and emit values without knowing about the graph, the schedule, or other nodes.

See also:

- [docs/module-implementation/implementation.md](../module-implementation/implementation.md) — how the harness turns a `run(...)` signature into ports, and the rules module authors follow
- [docs/module-implementation/testing.md](../module-implementation/testing.md) — testing modules in isolation
- [docs/contracts/index.md](../contracts/index.md) — the scheduling policies nodes are paired with
- [doc-structure.md](doc-structure.md) — the per-module doc file format

## Module reference

Modules are registered by plugin name in `modules/config.yaml`. Each documented module links to its own page; see [doc-structure.md](doc-structure.md) for what those pages cover.

### `modules/funcs.py` — reusable functional modules

| Module | Summary |
|---|---|
| `add` | integer addition |
| `alu` | integer ALU (add / subtract / multiply) |
| `dirname` | extract the parent directory of a path |
| `dirjoin` | join a directory and a filename into a path |
| `logger` | emit a value as a log event at a configurable level |
| `constant` | emit a configured constant value |

### `modules/io.py` — I/O modules

| Module | Summary |
|---|---|
| `fileread` | read a file from a configured path |
| `stdout` | print a value to stdout |

### `modules/rtl_buddy/setup.py` — config parsing, test selection, model loading

| Module | Summary |
|---|---|
| [discover-config-file](discover-config-file.md) | locate `root_config.yaml` by ascending from CWD |
| [prepend-cwd-path](prepend-cwd-path.md) | resolve a relative path against the working directory |
| [parse-root-config](parse-root-config.md) | parse `root_config.yaml` into a `RootConfig` |
| [select-platform](select-platform.md) | pick the platform entry matching the host `uname` |
| [resolve-builder](resolve-builder.md) | resolve the builder from the platform or CLI override |
| [work-dir](work-dir.md) | emit the working directory |
| [ensure-logs-dir](ensure-logs-dir.md) | create the logs subdirectory |
| [parse-suite-config](parse-suite-config.md) | parse the test suite YAML |
| [derive-seed-mode](derive-seed-mode.md) | derive the seed mode from `--rnd-new` / `--rnd-last` |
| [derive-randtest-runs](derive-randtest-runs.md) | derive run ids and seed mode from `rnd_cnt` / `--rnd-rpt` |
| [resolve-reg-config-path](resolve-reg-config-path.md) | resolve the regression config path from the CLI or root config |
| [parse-reg-config](parse-reg-config.md) | parse `regressions.yaml` into one suite config path per entry |
| [list-test-names](list-test-names.md) | print test names from the suite and exit |
| [select-tests](select-tests.md) | select tests from the suite by name or all |
| [filter-reglvl](filter-reglvl.md) | filter tests by register level |
| [resolve-model-ref](resolve-model-ref.md) | resolve a test's model name and config path |
| [load-model](load-model.md) | load a model configuration from `models.yaml` |
| [expand-sweep](expand-sweep.md) | expand a test into sweep variants via a hook script |
| [git-status](git-status.md) | capture the repo's git status for logging |

### `modules/rtl_buddy/build.py` — filelist pipeline, compile

| Module | Summary |
|---|---|
| [run-preproc](run-preproc.md) | run a test's preproc hook script |
| `filelist-extract` | extract filelist entries from a model or testbench config |
| `filelist-normalise` | relativise paths and warn on missing files |
| `filelist-flatten` | reduce each path to its basename |
| `filelist-strip` | drop the option prefix from each entry |
| `filelist-dedup` | remove duplicate entries |
| `prioritised-merge` | merge filelist entry lists by configured priority |
| `filelist-path` | compute the output `.f` path for a test |
| [write-filelist](write-filelist.md) | render entries to a `.f` file |
| [run-process](run-process.md) | run a subprocess with timeout and log capture |
| [build-compile-cmd](build-compile-cmd.md) | build the compile command from builder config and test |
| [interpret-compile](interpret-compile.md) | interpret the compile subprocess result |

### `modules/rtl_buddy/sim.py` — simulation, post-processing

| Module | Summary |
|---|---|
| [expand-runs](expand-runs.md) | fan a test out into multiple simulation runs |
| [resolve-seed](resolve-seed.md) | resolve the random seed for a run |
| [build-sim-cmd](build-sim-cmd.md) | build the simulation command |
| [write-randseed](write-randseed.md) | persist the resolved seed to a `.randseed` file |
| [link-latest](link-latest.md) | maintain `test.*` symlinks to the latest run's outputs |
| [interpret-sim](interpret-sim.md) | interpret the simulation subprocess result |
| [route-post](route-post.md) | route to UVM or plain log parsing |
| [parse-log](parse-log.md) | parse a plain simulation log into a verdict |
| [parse-uvm-log](parse-uvm-log.md) | parse a UVM simulation log into a verdict |

### `modules/rtl_buddy/control.py` — flow control

| Module | Summary |
|---|---|
| [early-stop-gate](early-stop-gate.md) | gate a test based on `--early-stop` depth |
| `flag-gate` | route a value to `on` or `off` based on a boolean flag |

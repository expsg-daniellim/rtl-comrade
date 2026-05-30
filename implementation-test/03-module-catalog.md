# Module catalog

Each module is the smallest sensible unit of node-local work. Every `run()` parameter is
one input port the harness can see; branches are expressed as named output ports; **no
module contains scheduling** (no guards, no awareness of other items). Signatures follow
the repo style (no space before the annotation colon, British spelling). "Tags" are
documentation-level labels (the manifest has no tag field — see
[07](07-ambiguities-and-assumptions.md)); they replace the old phase structure.

Conventions: `ctx`, `command`, `proc`, `seed`, `filelist`, `result` are the payload shapes
from [02](02-payload-conventions.md). **Contract** is the recommended pairing
([04](04-pipeline-and-contracts.md)).

---

## Setup / config

> **Reimplemented, not wrapped.** Per [07](07-ambiguities-and-assumptions.md) item 1, these
> modules reimplement `rtl_buddy`'s behaviour natively; only the **config schema** (the YAML
> field names/structure of `root_config.yaml`, `tests.yaml`, `models.yaml`) is preserved, so
> existing config files load drop-in. Reimplementing is what lets the monolithic loaders be
> split into the atomic, reusable nodes below.

### `discover-config-file`  · tags: setup · contract: `unit`
Walk up the directory tree from CWD for a filename, stopping at the git root / filesystem
root. Generic and reusable (the harness itself locates `rtl_comrade_config.yaml` this way).

- **Config:** `filename:str` (e.g. `root_config.yaml`), `max_levels:int = 8`
- **In:** — (zero-input; runs once)
- **Out:** default → `Path`

### `parse-root-config`  · tags: setup · contract: `unit`
Deserialise the root-config YAML into schema-compatible dataclasses (preserving rtl_buddy
field names: `rtl-buddy-filetype`, `cfg-rtl-builder`, `cfg-platforms`, …).

- **In:** `path:Path`
- **Out:** default → `root_cfg`

### `select-platform`  · tags: setup · contract: `unit`
Run `uname` and match it against each platform's `unames`; pick the platform. Side-effecting
(subprocess), runs once.

- **In:** `root_cfg`
- **Out:** default → `platform_cfg`

### `resolve-builder`  · tags: setup · contract: `unit`
Resolve the active builder from the platform (honouring the `--builder` override); critical
if the named builder is missing.

- **In:** `platform_cfg`, `builder:str = ""`
- **Out:** default → `builder_cfg`

### `parse-suite-config`  · tags: setup · contract: `unit`
Deserialise `tests.yaml` into the schema-compatible suite (testbenches + tests), binding each
test to its testbench (within-file) and recording the suite directory on each test so
`load-model` can resolve `model_path` later. Model loading is deferred to `load-model`.

- **In:** `test_config:str = "tests.yaml"`
- **Out:** default → `suite_cfg`

### `derive-seed-mode`  · tags: setup · contract: `unit`
Collapse the two bool flags into one `SeedMode` (`rnd_new` wins, else `DEFAULT`).

- **In:** `rnd_new:bool = False`, `rnd_last:bool = False`
- **Out:** default → `SeedMode`

---

## Selection / expansion (fan-out)

### `route-list-mode`  · tags: select · contract: `unit`
Routes on the `--list` flag (a global mode): `list` → the `list-test-names` terminal,
`run` → `select-tests`. A pure named-port classifier, so neither downstream needs a guard.

- **In:** `suite_cfg`, `list:bool = False`
- **Out:** `("run", suite_cfg)` | `("list", suite_cfg)`

### `list-test-names`  · tags: select · contract: `unit`
Print the suite's test names. Terminal — emits nothing, so in list-mode the whole pipeline
drains and exits 0.

- **In:** `suite_cfg`
- **Out:** none

### `select-tests`  · tags: select · contract: `unit`
Select one test or all (`get_tests(test_name)`) and yield one `ctx` per test, stamping
`key`. No mode logic — `--list` is handled upstream by `route-list-mode`.

- **In:** `suite_cfg`, `test_name:str = ""`
- **Out:** default → `ctx` per test

```python
class SelectTestsMod:
    def run(self, suite_cfg, test_name:str = ""):
        for t in suite_cfg.get_tests(test_name or None):
            yield ("default", { "key": t.get_name(), "test": t })
```

### `filter-reglvl`  · tags: select · contract: `default` (persistent: `builder_cfg`,`reg_level`,`start_level`)
`TestConfig.get_reglvl(builder)`. Emits on `skip` (a `result` payload) when outside the
`[start_level, reg_level]` window, else on `keep`. For `test`, `reg_level`/`start_level`
default to `None`, so it always emits `keep`; the node exists so `regression` reuses it.

- **In:** `ctx`, `builder_cfg`, `reg_level=None`, `start_level=None`
- **Out:** `("keep", ctx)` | `("skip", result)`

### `load-model`  · tags: select · contract: `default`
Load the test's `models.yaml` (resolving `model_path` relative to the suite dir recorded by
`parse-suite-config`) and attach the `ModelConfig` to `ctx["test"]`. Deferred from suite
parse so it is per-test and reusable (the `filelist` command needs the same step).

- **In:** `ctx`
- **Out:** default → `ctx` (test now carries its model)

### `expand-sweep`  · tags: expand · contract: `default` (persistent: `root_cfg`)
Reimplements `_expand_tests_with_sweep`'s `exec` pattern. No sweep → emit the one `ctx`
unchanged. Else yield one refined `ctx` per produced `TestConfig`.

- **In:** `ctx`, `root_cfg`
- **Out:** default → `ctx` per variant (key suffixed `#i`)

---

## Per-test preparation

### `run-preproc`  · tags: pre · contract: `default` (persistent: `root_cfg`)
Reimplements `VlogSim.pre`: if the test has a `preproc` script, `exec` it to mutate the test.

- **In:** `ctx`, `root_cfg`
- **Out:** default → `ctx`

### `write-filelist`  · tags: compile · contract: `default`
Reimplements `VlogFilelist.write_output(unroll=True, deduplicate=True)`. Emits the `ctx`
unchanged **and** the filelist payload on a second port (both consumed in lockstep by
`build-compile-cmd`, so no join is needed there).

- **In:** `ctx`
- **Out:** `("ctx", ctx)`, `("filelist", {key, filelist})`
- **Caveat:** `rtl_buddy` writes one `run.f` in CWD → collides under concurrency.
  Recommend a per-test `run.<tag>.f`; see [07](07-ambiguities-and-assumptions.md).

---

## The reusable subprocess core

### `build-compile-cmd`  · tags: compile · contract: `default` (persistent: `builder_cfg`,`builder_mode`)
Assembles the compiler argv as `VlogSim.compile`:
`[exe] + compile_time_opts(mode) + (["--Mdir", obj_dir] if verilator) + plusdefines + ["-f", run.f]`.
It has the builder + test, so it also computes the prospective `build_dir`, `simv` path, and
the compile log paths (`logs/<test>.compile.log`/`.err`) — folds `build_dir`/`simv` into
`ctx` and puts the log paths into `command` so `run-process` redirects there.

- **In:** `ctx`, `filelist`, `builder_cfg`, `builder_mode:str = "debug"`
- **Out:** `("ctx", ctx + {build_dir, simv})`, `("command", {key, argv, stdout_path, stderr_path})`

### `run-process`  · tags: compile, sim  ← **the reusable star**
Run a command's argv as an async subprocess, **redirecting** stdout/stderr to the files named
in the command (not buffering them in memory). Returns `rc`/`timed_out` and echoes the paths.
Redirecting means a timed-out run keeps whatever it wrote before the SIGQUIT, and memory is
bounded regardless of log size. Optionally enforces a timeout (SIGQUIT to the process group +
`rc=4444`). Used as two node instances (compile: no timeout; sim: with timeout).

- **In:** `command:{key,argv,stdout_path,stderr_path}`, `timeout:float | None = None`
- **Out:** default → `proc:{key,rc,timed_out,stdout_path,stderr_path}`

```python
class RunProcessMod:
    async def run(self, command:dict, timeout:float | None = None):
        with open(command["stdout_path"], "wb") as out, open(command["stderr_path"], "wb") as err:
            proc = await asyncio.create_subprocess_exec(*command["argv"],
                     stdout=out, stderr=err, preexec_fn=os.setpgrp)
            try:
                await asyncio.wait_for(proc.wait(), timeout)
                rc = proc.returncode
            except asyncio.TimeoutError:
                os.killpg(proc.pid, signal.SIGQUIT); await proc.wait(); rc = 4444
        return { "key": command["key"], "rc": rc, "timed_out": rc == 4444,
                 "stdout_path": command["stdout_path"], "stderr_path": command["stderr_path"] }
```

It emits **paths, not open handles** — the files close when the process exits and live
handles don't survive across async queue edges; downstream re-opens by path. The opaque `key`
is carried for correlation only — `run-process` never reads or branches on it.

### `interpret-compile`  · tags: compile · contract: `keyed_join` (`key_field: key`)
Joins the direct `ctx` edge with the subprocess `proc` by key. `rc == 0` → emit `ok`
(`simv` is already in `ctx`, folded in by `build-compile-cmd`). `rc != 0` → emit `fail`
(`CompileFailResults`; reads `proc["stderr_path"]`/`stdout_path` and logs at ERROR, as
`rtl_buddy`). Takes only the two keyed ports — no config port, since `keyed_join` joins
*every* port by key.

- **In:** `ctx`, `proc`
- **Out:** `("ok", ctx)` | `("fail", result)`

---

## Run expansion (fan-out per run-id)

### `expand-runs`  · tags: sim · contract: `default` (persistent: `run_ids`)
One compiled test → one `ctx` per run-id (key suffixed `#run`, `run_id` recorded). For
`test`, `run_ids=[None]` → a single passthrough.

- **In:** `ctx`, `run_ids=[None]`
- **Out:** default → `ctx` per run-id

---

## Simulation

### `resolve-seed`  · tags: sim · contract: `default` (persistent: `seed_mode`,`builder_cfg`)
`VlogSim.execute` seed logic: `NEW`→`random.randrange(1_000_000)`,
`DEFAULT`→`builder_cfg.get_seed()`, `REPLAY`→read `logs/<test>[_NNNN].randseed`. Emits the
`ctx` unchanged **and** the seed (lockstep → `build-sim-cmd` needs no join).

- **In:** `ctx`, `seed_mode`, `builder_cfg`
- **Out:** `("ctx", ctx)`, `("seed", {key, seed})`

### `build-sim-cmd`  · tags: sim · contract: `default` (persistent: `builder_cfg`,`builder_mode`)
`VlogSim.execute` argv: `[simv] + run_time_opts(mode, seed) + plusdefines + plusargs`; also
computes the per-test `timeout` from `TestConfig.get_timeout()` and the sim log paths
(`logs/<test>[_NNNN].log`/`.err`). Folds `seed` and the `log` path into `ctx` (needed by
`write-randseed` and `post`) and puts the log paths into `command` so `run-process` redirects
there.

- **In:** `ctx`, `seed`, `builder_cfg`, `builder_mode`
- **Out:** `("ctx", ctx + {seed, log})`, `("command", {key, argv, stdout_path, stderr_path})`, `("timeout", float)`

*(then `run-process` again, wired with the `timeout` input)*

> The sim `.log`/`.err` are written by `run-process` itself (it redirects there), so there
> is no separate "write-sim-logs" module — the log writer **is** the generic runner. The two
> remaining post-sim concerns (per directive 1: randseed and symlinks are distinct) become
> their own nodes. The first of them holds the `ctx ⋈ proc` join.

### `write-randseed`  · tags: sim · contract: `keyed_join` (`key_field: key`)
The sim's join point: pairs `ctx` (carrying `seed`) with the sim `proc` by key. Writes
`logs/<test>[_NNNN].randseed` from `ctx["seed"]` (plus `HierInstanceSeed.txt` contents when
present). Folds `rc`/`timed_out` from `proc` into `ctx` for the two nodes after it.

- **In:** `ctx`, `proc`
- **Out:** default → `ctx + {rc, timed_out}`

### `link-latest`  · tags: sim · contract: `default`
Force the stable `test.log`/`test.err`/`test.randseed` symlinks in CWD to this run's files
(known from `ctx`). Runs after `write-randseed` so the `.randseed` target exists. Distinct
functionality from randseed writing.

- **In:** `ctx`
- **Out:** default → `ctx`

### `interpret-sim`  · tags: sim · contract: `default`
Pure routing on the joined result: `timed_out` → `timeout` (`SimTimeoutResults`), else `ok`.
No side-effects — the artifacts were written upstream.

- **In:** `ctx`
- **Out:** `("ok", ctx)` | `("timeout", result)`

---

## Post-processing

### `route-post`  · tags: post · contract: `default`
Classifies on `ctx["test"].uvm`: emit `uvm` when a `UVMConfig` is present, else `plain`.
Pure data classification expressed as a named-port return (like `interpret-compile` on
`rc`) — not scheduling. This is the only place the uvm/plain decision lives.

- **In:** `ctx`
- **Out:** `("uvm", ctx)` | `("plain", ctx)`

### `parse-log`  · tags: post · contract: `default`
Reimplements `VlogPost` only: the `PASS/FAIL/ERR/FAT` regex scan. Emits `{key, result}`.

- **In:** `ctx`
- **Out:** default → `result`
- **Note:** inherits `rtl_buddy`'s `VlogPost` quirks (PASS wins over FAIL; a FAIL line with
  no ERR/FAT raises). No `postproc` script is run (parity). See [07](07-ambiguities-and-assumptions.md).

### `parse-uvm-log`  · tags: post · contract: `default`
Reimplements `UvmVlogPost` only: parse the UVM Report Summary severity counts and compare against
`ctx["test"].uvm.max_warns`/`max_errors` (FATAL must be 0). Emits `{key, result}`.

- **In:** `ctx`
- **Out:** default → `result`

---

## Control / aggregation

### `early-stop-gate`  · tags: (cross-cutting) · contract: `default` (persistent: `early_stop`)
Compare the global `early_stop` phase against this gate's configured `phase`. Stop here →
emit `stop` (`EarlyStopResults`); else `go`. Three instances differing only in config.

- **In:** `ctx`, `early_stop:str = "post"`
- **Config:** `phase:str` (`pre`|`comp`|`sim`)
- **Out:** `("go", ctx)` | `("stop", result)`

### `aggregate-results`  · tags: report · contract: **`merge`** + `finalise()`
The single collector. The `merge` contract (see [05](05-branching-and-results.md)) drains
its many terminal-result ports, delivering one `result` per invocation under whichever port
fired. `run` accumulates; `finalise` prints the summary and logs `ERROR` if any result is
not `is_pass()` (harness maps a single ERROR → exit 1, reproducing the OR-accumulated exit
code).

- **In:** `**results` (one terminal-result port per source — see the edge list in [06](06-graph-yaml.md))
- **Out:** none (sink)

```python
class AggregateResultsMod:
    def __init__(self):
        self._rows = []
    def run(self, **fired):                 # merge delivers exactly one {port: result}
        for payload in fired.values():
            self._rows.append(payload)
    def finalise(self):
        for r in self._rows:
            res = r["result"]
            log.info("test_result", key=r["key"],
                     result=res.results["result"], desc=res.results["desc"])
        failed = [ r for r in self._rows if not r["result"].is_pass() ]
        if failed:
            log.error("suite_has_failures", n=len(failed))
```

## Module → rtl_buddy provenance

All modules **reimplement** the rtl_buddy source natively; only the config schema is kept
identical (07, item 1).

| module | reimplements (rtl_buddy source) |
|---|---|
| `discover-config-file` | `_discover_root_cfg` upward walk |
| `parse-root-config` | `RootConfigFile` deserialisation |
| `select-platform` | `RootConfig` `uname`/platform match |
| `resolve-builder` | `PlatformConfig.initialise` builder resolution |
| `parse-suite-config` | `SuiteConfigFile` parse + testbench bind |
| `load-model` | `ModelConfigLoader.get_model` (per test) |
| `derive-seed-mode` | `rnd_new/rnd_last` → `SeedMode` in `do_cmd_test` |
| `route-list-mode` | the `--list` branch in `do_cmd_test` |
| `list-test-names` | `--list` echo of `get_test_names()` |
| `select-tests` | `SuiteConfig.get_tests` |
| `filter-reglvl` | `_do_test_suite` level filter + `SkipResults` |
| `expand-sweep` | `_expand_tests_with_sweep` |
| `run-preproc` | `VlogSim.pre` |
| `write-filelist` | `VlogFilelist.write_output` |
| `build-compile-cmd` | `VlogSim.compile` argv assembly |
| `run-process` | `VlogSim.compile`/`execute` subprocess + output redirect |
| `interpret-compile` | `VlogSim.compile` rc check + `CompileFailResults` |
| `expand-runs` | `TestRunner.run` vs `run_multiple` run-id loop |
| `resolve-seed` | `VlogSim.execute` seed resolution (all modes) |
| `build-sim-cmd` | `VlogSim.execute` argv + timeout |
| `write-randseed` | `VlogSim.execute` `.randseed` write |
| `link-latest` | `VlogSim.execute` `test.log`/`.err`/`.randseed` symlink forcing |
| `interpret-sim` | `VlogSim.execute` timeout check |
| `route-post` | the `if test.uvm` dispatch inside `VlogSim.post` |
| `parse-log` | `VlogPost` |
| `parse-uvm-log` | `UvmVlogPost` |
| `early-stop-gate` | `RunDepth`/`--early-stop` + `EarlyStopResults` |
| `aggregate-results` | `do_cmd_test` summary + exit OR + `typer.Exit` |

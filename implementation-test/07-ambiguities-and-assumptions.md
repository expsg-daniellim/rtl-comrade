# Ambiguities, assumptions, and open questions

A current snapshot. Items confirmed in earlier turns are recorded under **Settled** so future
readers don't relitigate. **Open** items genuinely await your call. **To verify** items are
empirical framework checks the implementation owner should run before building. **Notable
divergences** is the deliberate-changes-from-`rtl_buddy` audit. **Implementation notes** are
informational.

## Settled

1. **Reimplement `rtl_buddy`; preserve only the config surface.** Modules reimplement the
   behaviour natively (no importing `RootConfig`/`SuiteConfig`/`VlogSim`/`VlogPost`/…). The
   one thing kept identical is the **YAML config schema**: field names/structure of
   `root_config.yaml`, `tests.yaml`, `models.yaml`, and `regressions.yaml` —
   e.g. `rtl-buddy-filetype`, `cfg-rtl-builder`, `builder-opts`, `reglvl`, `plusargs`,
   `plusdefines`, `testbench`, `model_path` — so existing config files load drop-in. This is
   what lets the monolithic loaders split into atomic nodes (`discover-config-file`,
   `parse-root-config`, `select-platform`, `resolve-builder`, `parse-suite-config`,
   `load-model`). `TestResults` and `SeedMode` are reimplemented as a thin shared schema.

2. **Hybrid correlation strategy.** Main-line `ctx` is `{key, test}` plus values *every*
   downstream stage needs (`simv` after compile; `seed`/`log` after sim-build). Derived or
   transient values (argv, rc, log bytes, `result`) never enter `ctx`. The only
   `keyed_join`s are `cc-int` and `randseed` — exactly where a fast `ctx` path meets a slow
   subprocess `proc` path. Everywhere else is single-source lockstep on `default`.

3. **Custom `merge` contract for terminal fan-in.** The eight mutually-exclusive terminal
   outcomes re-converge through an authored non-correlating `merge` contract (forward any
   port; end when all end). No built-in expresses mutually-exclusive exits — see
   [05](05-branching-and-results.md).

4. **`run-process` redirects to caller-supplied files; emits paths.** stdout/stderr go
   straight to files named in `command`, so partial output survives a SIGQUIT and memory
   stays bounded regardless of log size. It carries an opaque correlation `key` (never read
   or branched on) so downstream `keyed_join` can match `proc` to `ctx`. Used as two node
   instances (compile/sim).

5. **Post-sim trio (atomic split).** `write-randseed` writes `.randseed` and holds the
   sim-side `keyed_join`; `link-latest` forces the `test.*` symlinks (distinct functionality
   per directive); `interpret-sim` is pure routing on `timed_out`. The `.log`/`.err` files
   are written by `run-process` itself — there is no separate "logs writer" module.

6. **Post-parse split.** `route-post` (classifies on `ctx["test"].uvm`) + `parse-log`
   (`VlogPost`) + `parse-uvm-log` (`UvmVlogPost`). The two parsers are atomic and
   independently reusable; the uvm/plain decision lives in one router.

7. **List-mode split.** `route-list-mode` + `list-test-names` + a pure `select-tests`.
   `--list` is routing off the main line, not an `if list:` inside `select-tests`.

8. **`load-model` is lazy** (per-test, after `filter`). Accepted as a behavioural upgrade —
   skipped tests no longer pay for (or fail on) their `models.yaml`.

9. **No scheduling in modules.** Branches are named output ports; correlation lives in
   `keyed_join`; fan-in lives in `merge`; persistent config lives in the `default` contract.
   No envelope, no passthrough guards, no `result` field on the main line.

10. **Exit code via logging.** `aggregate-results.finalise()` logs ERROR if any row is not
    `is_pass()` → harness exits 1 (reproducing rtl_buddy's OR-accumulated exit code). PASS
    and SKIP contribute nothing. CRITICAL is reserved for fatal config errors (matching
    `logger.critical` → `typer.Abort`).

11. **`--debug`/`--color` dropped.** `rtl-comrade` owns logging via `--level`; only the
    genuinely test-affecting globals (`--builder-mode`, `--builder`, `--early-stop`) survive
    as CLI edges. Easy to revert if you want them back.

12. **Compile logs persisted to files** (accepted as an improvement). Compile output now
    lives in `logs/<test>.compile.log`/`.err`, a direct consequence of `run-process` always
    redirecting. Better for debugging than rtl_buddy's captured-and-logged-only behaviour.

13. **`test_name` is a true optional positional** — to match rtl_buddy's CLI surface. CLI
    edge uses `option: false` with `default: ""` (empty = run all tests).

14. **`postproc` script not run** (parity with rtl_buddy, which parses `postproc_path` but
    never executes it). `parse-log`/`parse-uvm-log` do built-in parsing only.

## Open — needs your call

15. **VlogPost quirks: replicate or fix?** rtl_buddy's `VlogPost` lets PASS win over FAIL when
    both appear, and raises if a `FAIL` line has no matching `ERR:`/`FAT:`. Faithfully copying
    inherits both. The uvm path is in the separate `parse-uvm-log` and is unaffected.

16. **Sibling graphs.** Plain `test` defaults `expand-runs` to `[None]`. Want me to also
    design the `randtest` graph (adds `rnd_cnt`/`rnd_rpt`) and the `regression` graph (adds
    `reg_level`/`start_level` wiring + outer suite loop + per-suite `chdir`)?

## Deferred (KIV)

17. **Concurrency / shared CWD paths** — *deferred pending an upstream rtl_buddy change* that
    runs each compile and sim command in its own subdirectory. Once that lands, the
    collisions that the graph's structural concurrency would otherwise expose (`run.f`,
    `obj_dir_<tag>/`, `test.*` symlinks, `rtl_buddy.log`) go away. Keep `run-process` and the
    sim-side nodes ready to honour per-invocation working dirs.

18. **Seed mode plumbing** — CLI surface kept as two bool flags (`-n`/`--rnd-new`,
    `-l`/`--rnd-last`) per rtl_buddy parity. Planned direction (KIV): move input validation
    into the randseed-generating module (`resolve-seed`) so it can directly accept a string
    seed-mode argument, allowing `derive-seed-mode` to be absorbed if/when the CLI moves to a
    single string. No structural change now.

## To verify against the framework before building

19. **`merge` + `**kwargs` port inference.** `aggregate-results.run(self, **fired)` relies on
    the harness accepting an open port set from `**kwargs` and `merge` delivering one
    `{firing_port: payload}`. If `structure.py` won't accept that, declare the eight port
    names explicitly with `=None` defaults.

20. **`merge` contract correctness.** The sketch in [05](05-branching-and-results.md) keeps
    one in-flight `get()` per open port on `self` so no item is lost between `get_inputs`
    calls. Review carefully under the real `ContractPort` API — end-sentinel handling and
    task lifetime are the risk areas.

21. **`default` + persistent port with no upstream edge.** `filter`'s `reg_level`/`start_level`
    are listed persistent but unwired for the `test` graph (relying on Python defaults `None`).
    Verify graph validation accepts that; if not, omit them from `persistent_inputs` here
    and wire them only in the `regression` graph.

22. **`keyed_join` payload delivery.** Modules at the joins (`cc-int`, `randseed`,
    `interpret-compile`) read `ctx["test"]` / `proc["rc"]` etc. — confirm `keyed_join`
    delivers the dict payloads to the module unwrapped from `Payload` as expected.

23. **Async subprocess hardening.** `run-process` is async so it doesn't block the loop; the
    `setpgrp`/`SIGQUIT` handling and the `rc=4444` timeout sentinel need care under asyncio
    (the [03](03-module-catalog.md) sketch is indicative, not final).

## Notable divergences from rtl_buddy

- **`load-model` is lazy** (settled 8) — broken `models.yaml` in a skipped test no longer
  errors early.
- **Compile output is persisted to files** (settled 12) as a side effect of the redirect.
- **Concurrency is structurally available** (deferred 17) — pending an upstream rtl_buddy
  change to per-invocation subdirectories.
- **`postproc_path` not executed** (settled 14) — parity with rtl_buddy.
- **`VlogPost` quirks inherited unless fixed** (open 15).
- **`--debug`/`--color` flags not exposed** (settled 11) — logging owned by harness
  `--level`.

## Implementation notes

- **`--early-stop` phase ordering**: `pre < comp < sim < post`; mirror rtl_buddy's `RunDepth`.
  Each `early-stop-gate` compares against this ordering.
- **Tags have no manifest field.** `pre/compile/sim/post` are documentation labels only;
  first-class tags would need a manifest + loader extension.
- **Config objects cross edges as live Python objects** (`RootConfig`, `TestConfig`, …). Fine
  for asyncio; would need to be picklable only if the harness ever went multiprocess.
- **CWD assumptions preserved.** `root_config.yaml` discovery walks up from CWD; `run.f`,
  `obj_dir`, `logs/` are CWD-relative — same as rtl_buddy. `regression`'s per-suite `chdir`
  is out of scope for the `test` graph.
- **`.` prepended to `$PATH`.** rtl_buddy does this so a CWD-local simulator is found.
  `run-process` (or a setup node like `resolve-builder`) must replicate it or
  `verilator`/`simv` discovery breaks.
- **`exec`'d preproc/sweep scripts reproduced as-is.** `run-preproc`/`expand-sweep` emit the
  mutated/expanded `TestConfig` in `ctx`, not via hidden global mutation.
- **`keyed_join` cannot hold a persistent config port** (it joins every port by key). That's
  why `simv`/`seed`/`log` are folded into `ctx` by the command builders upstream rather than
  delivered as a config port to the join nodes.
- **`discover-config-file` is reusable for the harness's own config.** The harness already
  locates `rtl_comrade_config.yaml` by walking up the tree — worth sharing one implementation.

## Process note

This plan was developed without reading `test-implementation/` (your existing plan) or
`graphs/graph3.yaml` (the graph already wired to the `test` command), so it is independent
and comparable to yours.

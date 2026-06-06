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

2. **Correlation strategy.** `ctx` starts as `{key, test, run_id}` from `select`;
   `build-compile-cmd` adds `simv`, giving `{key, test, run_id, simv}`. No further fields
   are added after that point. `seed`/`log`/`err`/`randseed_path` travel as
   `sim_cmd = {key, seed, log, err, randseed_path}` emitted by `sim-build`.
   `write-randseed` is a 3-port `keyed_join` (`ctx`, `proc`, `sim_cmd`) that assembles
   `test_run = {key, test, run_id, rc, timed_out, log, err, randseed_path}` once; all
   post-sim nodes receive `test_run`. The only `keyed_join`s are `cc-int` (2 ports) and
   `randseed` (3 ports). Everywhere else is single-source lockstep on `default`.

3. **`fan-in-results` module + `any` contract for terminal fan-in.** The 13 mutually-exclusive
   terminal outcomes re-converge through a `fan-in-results` relay module (`**kwargs`,
   edge-derived ports) paired with a general-purpose `any` contract (forward whichever
   port is ready; end when all end). No built-in expresses mutually-exclusive exits — see
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
   `keyed_join`; fan-in lives in the `any` contract (on `fan-in-results`); persistent
   config lives in the `default` contract. No envelope, no passthrough guards, no `result`
   field on the main line.

10. **Exit code via logging.** `aggregate-results.finalise()` logs ERROR if any row is not
    `is_pass()` → harness exits 1 (reproducing rtl_buddy's OR-accumulated exit code). PASS
    and SKIP contribute nothing. CRITICAL is reserved for fatal config errors (matching
    `logger.critical` → `typer.Abort`). Per-test config-domain failures (`load-model`
    missing/malformed, `write-filelist` source-not-found, `expand-sweep` exec crash,
    `run-preproc` exec crash, `resolve-seed` REPLAY missing/malformed `.randseed`) route
    via a new `fail` output port to merge and additionally call `log.error` at emission
    (belt-and-braces — `handler.failure` is set both at the emission site and again at
    `finalise()`). `run-process` subprocess-launch failure (binary not on PATH, permission
    denied) is `log.critical` (system-wide, not per-test). Parse-machinery exceptions
    distinct from FAIL classification are deferred pending item 15. Full per-site table
    in [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

11. **`--debug`/`--color` dropped.** `rtl-comrade` owns logging via `--level`; only the
    genuinely test-affecting globals (`--builder-mode`, `--builder`, `--early-stop`) survive
    as CLI edges. Easy to revert if you want them back.

12. **Compile logs persisted to files** (accepted as an improvement). Compile output now
    lives in `<logs_dir>/<test>.compile.log`/`.err` (default `logs/<test>...`,
    overridable via `--logs-dir` per Settled 26), a direct consequence of `run-process`
    always redirecting. Better for debugging than rtl_buddy's captured-and-logged-only
    behaviour.

13. **`test_name` is a true optional positional** — to match rtl_buddy's CLI surface. CLI
    edge uses `option: false` with `default: ""` (empty = run all tests).

14. **`postproc` script not run** (parity with rtl_buddy, which parses `postproc_path` but
    never executes it). `parse-log`/`parse-uvm-log` do built-in parsing only.

15. **`ParseLogMod` corrects all three `VlogPost` quirks** (settled 2026-06-05). Decision:
    fix, not replicate. Three corrections applied to `ParseLogMod` in
    [spec 09](specs/09-post-modules.md):
    (1) **Word-boundary guard**: `re.match(r"PASS\b\s*(.*)", line)` and
    `re.match(r"FAIL\b\s*(.*)", line)` replace rtl_buddy's `re.search(r"^PASS\s*(.*)")` /
    `re.search(r"^FAIL\s*(.*)")` so `PASSTHROUGH`/`FAILING` do not misclassify.
    (2) **FAIL wins over PASS**: `if match_fail … elif match_pass …` replaces the two
    independent `if` blocks so a log containing both `PASS` and `FAIL` lines resolves to
    FAIL regardless of order.
    (3) **Safe FAIL-without-ERR**: guard `match_err` when building `desc` — if `match_fail`
    is set but `match_err` is not, `desc = match_fail.group(1)` (no `AttributeError` on
    `None.group(2)`). `ParseUvmLogMod` (`UvmVlogPost` path) is unaffected — its path has
    no equivalent quirks.

16. **Sibling graphs are a modularity analysis, not deliverables** (settled 2026-06-05).
    `08-sibling-graphs.md` shows that the core module catalogue supports `randtest` and
    `regression` with minimal additions: 1 new module for `randtest`; 2 new modules + 1
    contract switch for `regression` — see the
    [Summary section](08-sibling-graphs.md#summary). The sibling graphs are **not**
    deliverables of this plan; `08` is the design starting point when they are built.

19. **`fan-in-results` + `any` contract for terminal re-convergence** (revised 2026-06-05;
    originally settled 2026-05-31 as `MergeContract`). Earlier drafts had
    `aggregate-results.run(self, **fired)` rely on the harness inferring an open port set
    from `**kwargs`. `src/rtl_comrade/structure.py:115-119` shows a `VAR_KEYWORD`
    parameter produces one port literally named after the variable, not arbitrary
    inference. The non-definite-inputs mechanism (`graph.py:95-97`) resolves this cleanly:
    when a module's `run()` uses `**kwargs`, the harness populates its port set from graph
    edges at load time. Design: a `fan-in-results` relay module (`run(self, **inputs)`,
    13 edge-derived ports) paired with a general-purpose `any` contract (fire on any
    single ready port; end when all end). `aggregate-results` retains `run(self, result)`
    with `default`. No harness change required. Sketch and invariants in
    [05](05-branching-and-results.md). (Number kept at 19 to preserve cross-references.)

21. **`default` + persistent port with no upstream edge** (settled 2026-06-02). For
    `filter-reglvl`'s `reg_level`/`start_level` and `expand-runs`' `run_ids`, persistent
    inputs without an edge fall through to the Python default. Three doc citations
    settle it without a probe: `docs/harness/validation.md:39` ("every non-default input
    port has some incoming edge" — default-having ports are exempt from edge validation);
    `docs/contracts/default.md` invocation precedence step 4 ("Default-valued ports with
    nothing queued — omitted from the dict; Python's own default activates when the
    module is called"); `docs/modules/implementation.md` ("The built-in default contract
    can use such defaults without any upstream edge for that port"). No fallback design
    needed — `run_ids = [None]`, `reg_level = None`, `start_level = None` fire as written.
    (Number kept at 21 to preserve cross-references — sits in Settled despite being
    numerically out of order.)

22. **`keyed_join` payload delivery** (settled 2026-06-02). Modules at the two join nodes
    (`cc-int`, `randseed`) receive their keyed port payloads unwrapped — no `Payload`
    wrapper. `cc-int` receives `ctx` and `proc`; `randseed` receives `ctx`, `proc`, and
    `sim_cmd`. Settled by `docs/modules/implementation.md` Runtime Call Model:
    "the harness unwraps the payload objects to raw values" and "modules receive raw
    values, not `Payload` wrappers." The unwrap happens at `src/rtl_comrade/node.py:281`
    before `module.run(**inputs)` and is contract-agnostic, so `keyed_join` delivers raw
    dicts (matching the example in `docs/contracts/keyed_join.md`). No alternative payload
    shape needed. (Number kept at 22 to preserve cross-references — sits in Settled
    despite being numerically out of order.)

24. **CWD posture for `test`/`randtest`: user-driven + startup check** (settled
    2026-06-02). Parity with `rtl_buddy`: `do_cmd_test` never `chdir`s (only
    `do_rtl_regression` does, per-suite at `rtl_buddy/src/rtl_buddy/rtl_buddy.py:404`).
    The user is expected to `cd` into the suite directory before invoking
    `rtl-comrade test` / `randtest`, matching the `rtl_buddy/AGENTS.md` validation
    example (`cd .../verif && python -m rtl_buddy test basic`). A new setup node
    [`check-suite-cwd`](03-module-catalog.md) (spec
    [04](specs/04-setup-modules.md)) enforces the convention by failing fast with
    `log.critical` if `(Path.cwd() / test_config).resolve().parent != Path.cwd().resolve()`
    or if the resolved file doesn't exist. This catches `-c /abs/elsewhere/tests.yaml`,
    `-c ../sibling/tests.yaml`, and `-c subdir/tests.yaml` — three monorepo-mistarget
    cases that the existing `parse-suite-config` log.critical (file-missing only) does
    not catch. Wired in test and randtest graphs; **not** wired in regression (regression
    `chdir`s per-suite via `parse-reg-config` → `parse-suite-config`). The "CWD
    assumptions preserved" implementation note below is now explicit, not silent.

25. **`.`-prepend to `$PATH`: dedicated `prepend-cwd-path` setup node** (settled
    2026-06-02). `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102` mutates
    `os.environ["PATH"]` once at CLI bootstrap so a CWD-local simulator (`simv`,
    `verilator`) is discoverable. Plan B reproduces this as an explicit graph node:
    [`prepend-cwd-path`](03-module-catalog.md) (spec
    [04](specs/04-setup-modules.md)), a zero-input `unit` setup node that performs
    the same idempotent prepend and emits a `bool` sentinel on `default`.
    `run-process` declares a generic persistent input `env_ready:bool = True`; the
    graph wires `prepend-path → cc-run.env_ready` and `prepend-path → sim-run.env_ready`
    so the harness's data-dependency ordering pins the mutation strictly upstream of
    every subprocess (no race window). The input name is deliberately generic so any
    future env-setup node can join the same sequencing surface. **Considered and
    rejected**: (a) doing the mutation inside `run-process` (per-call, mutates
    process-wide state in the inner loop, widens the workhorse's responsibility);
    (b) doing it inside `resolve-builder` (widens a config-resolution module with
    env-policy concerns; no natural successor if future env-setup nodes are added).
    Wired in all three graphs (test/randtest/regression) — the mutation is harmless
    where unused and load-bearing where the simulator binary sits in CWD. Supersedes
    the "Implementation notes" entry of the same name below (now removed).

26. **`logs/` ownership, lifecycle, and `--logs-dir`** (settled 2026-06-02). The
    artefact directory is **owned by a single setup node**, not the writers. A new
    [`ensure-logs-dir`](03-module-catalog.md) (spec
    [04](specs/04-setup-modules.md)) `unit` node calls
    `Path(logs_dir).mkdir(parents=True, exist_ok=True)` once at startup; no other
    module calls `mkdir`. **Location is CWD-relative `logs/` by default** — parity
    with `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59`, where `VlogSim.__init__`
    lazily `makedirs`'s a hard-coded `"logs"` literal per test. Plan B lifts that
    into one explicit setup node so (a) no downstream writer needs `mkdir`, (b) the
    directory is materialised once per invocation rather than per `VlogSim`, and (c)
    the path becomes overridable. **`-L/--logs-dir`** (default `"logs"`) is a small
    Notable divergence from rtl_buddy (which has no override) — it broadcasts as a
    CLI edge to `ensure-logs-dir` (creates the directory) and to `build-compile-cmd`
    / `build-sim-cmd` / `resolve-seed` as persistent inputs (compose paths inside it).
    `write-randseed` does not consume `logs_dir` directly — `build-sim-cmd` emits
    `randseed_path` in `sim_cmd` so the `keyed_join` receives it as a dedicated keyed
    port (no persistent config port on keyed_join — see Implementation notes). **Sequencing**: the
    env-setup chain is now `prepend-path → ensure-logs → cc-run/sim-run.env_ready`,
    with an additional `check-cwd → ensure-logs._cwd` edge so a bad-CWD invocation
    aborts before any rogue `logs/` is materialised. **Lifecycle**: never auto-cleaned
    (parity); user owns purging. **Concurrency**: filenames within `logs/` are
    uniquely keyed by `<test_name>[_NNNN]` (sweep + run-id), so no within-directory
    collisions even when the [item 17](07-ambiguities-and-assumptions.md) interim
    shim is in effect. Wired in `test`/`randtest` only — `regression`'s per-suite
    `chdir` needs a per-suite bootstrap that lives in [08](08-sibling-graphs.md).
    The CWD-relative half of the "CWD assumptions preserved" Implementation notes
    entry below is now explicit, not silent.

## Deferred (KIV)

17. **Concurrency / shared CWD paths** — *deferred pending an upstream rtl_buddy change* that
    runs each compile and sim command in its own subdirectory. Once that lands, the
    collisions that the graph's structural concurrency would otherwise expose (`run.f`,
    `obj_dir_<tag>/`, `test.*` symlinks, `rtl_buddy.log`) go away. Keep `run-process` and the
    sim-side nodes ready to honour per-invocation working dirs.

    **Interim posture (settled 2026-05-31; updated 2026-06-05).** Until the upstream change
    lands, the design serialises the compile/sim region via a process-wide `asyncio.Lock`:
    a new `serial_acquire` contract on `write-filelist` acquires once per (test,
    sweep-variant), and the `any` contract on `fan-in` carries an optional `release_lock`
    Config field that releases once per delivered terminal payload. Pre-region nodes still
    parallelise; the mid-region is single-test-at-a-time. Scoped to the plain `test` graph
    (R=1); `randtest`/`regression` need a different release rule. Mechanism, constraints,
    and removal plan in
    [05 — Serialising contracts](05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture).
    Both contract pieces are **explicitly temporary** and must be removed when this item
    moves out of Deferred.

18. **Seed mode plumbing** — CLI surface kept as two bool flags (`-n`/`--rnd-new`,
    `-l`/`--rnd-last`) per rtl_buddy parity. Planned direction (KIV): move input validation
    into the randseed-generating module (`resolve-seed`) so it can directly accept a string
    seed-mode argument, allowing `derive-seed-mode` to be absorbed if/when the CLI moves to a
    single string. No structural change now.

## To verify against the framework before building

20. **`any` contract correctness.** The sketch in [05](05-branching-and-results.md) keeps
    one in-flight `get()` per open port on `self` so no item is lost between `get_inputs`
    calls. Review carefully under the real `ContractPort` API — `EndSentinel` handling and
    task lifetime are the risk areas.

23. **Async subprocess hardening.** Design finalised in
    [`specs/03-run-process.md`](specs/03-run-process.md) (2026-05-31): SIGQUIT-to-group
    with `_TIMEOUT_GRACE_S` SIGKILL escalation, `rc=4444` sentinel with `timed_out` set
    independently, and explicit cancellation cleanup under `asyncio.shield`. **What
    remains to verify empirically** before the module is built: that the default
    `ThreadedChildWatcher` (Python 3.8+) reaps without explicit `waitpid`; that
    `os.killpg` race-with-already-exited (`ProcessLookupError`) actually surfaces under
    real load (not just contrived tests); that `asyncio.wait_for`'s inner cancellation
    of `proc.wait()` does not interfere with our subsequent `proc.wait()` reap. Plan B
    deliberately departs from rtl_buddy on (i) signalling the full process group rather
    than just the leader and (ii) adding SIGKILL escalation — record both under
    "Notable divergences" when implementation lands.

## Notable divergences from rtl_buddy

- **`load-model` is lazy** (settled 8) — broken `models.yaml` in a skipped test no longer
  errors early.
- **Compile output is persisted to files** (settled 12) as a side effect of the redirect.
- **Concurrency is structurally available** (deferred 17) — pending an upstream rtl_buddy
  change to per-invocation subdirectories. **Interim**: pre-region runs concurrently;
  the compile/sim region is held atomic per test by a `serial_acquire`/`any.release_lock`
  pair on `write-filelist`/`fan-in` (see item 17 and [05 — Serialising contracts](05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture)).
- **`postproc_path` not executed** (settled 14) — parity with rtl_buddy.
- **`VlogPost` quirks corrected in `ParseLogMod`** (settled 15) — word boundary after
  `PASS`/`FAIL`, FAIL wins over PASS when both appear, safe desc when `ERR:`/`FAT:` is
  absent. `ParseUvmLogMod` unaffected. See Settled item 15.
- **`--debug`/`--color` flags not exposed** (settled 11) — logging owned by harness
  `--level`.
- **`-L/--logs-dir` is a new CLI override** (settled 26). `rtl_buddy` hard-codes
  `"logs"` (`tools/vlog_sim.py:55`); Plan B keeps the same default but accepts a
  user-supplied path. Composition sites (`build-compile-cmd`, `build-sim-cmd`,
  `resolve-seed` REPLAY) take it as a persistent input; the bootstrap site
  (`ensure-logs-dir`) creates the directory once at startup.
- **Per-test config-domain failures route as per-test FAIL, not `logger.critical`**
  (settled 10). `load-model`, `write-filelist`, `expand-sweep`, `run-preproc`, and
  `resolve-seed` (REPLAY) emit on a new `fail` port with `log.error` instead of aborting
  the whole run. rtl_buddy `logger.critical`s on preproc-script and sweep-script crashes
  (`vlog_sim.py:134-137`, `rtl_buddy.py:279-281`); Plan B continues running other tests.
  REPLAY-missing already matches rtl_buddy's per-test FAIL via `log.error` + FAIL stub
  log (`vlog_sim.py:200-213`); the divergence is structural (port-routed `result`) not
  behavioural.

## Implementation notes

- **`--early-stop` phase ordering**: `pre < comp < sim < post`; mirror rtl_buddy's `RunDepth`.
  Each `early-stop-gate` compares against this ordering.
- **Tags have no manifest field.** `pre/compile/sim/post` are documentation labels only;
  first-class tags would need a manifest + loader extension.
- **Config objects cross edges as live Python objects** (`RootConfig`, `TestConfig`, …). Fine
  for asyncio; would need to be picklable only if the harness ever went multiprocess.
- **CWD assumptions preserved.** `root_config.yaml` discovery walks up from CWD; `run.f`,
  `obj_dir`, `logs/` (default, overridable via `--logs-dir` per Settled 26) are
  CWD-relative — same as rtl_buddy. The user must `cd` into the suite directory before
  invoking `rtl-comrade test`/`randtest`; the `check-suite-cwd` node enforces this (see
  Settled item 24). The `logs/` directory is materialised by `ensure-logs-dir` once at
  startup (Settled 26). `regression`'s per-suite `chdir` is out of scope for the
  `test`/`randtest` graphs.
- **`exec`'d preproc/sweep scripts reproduced as-is.** `run-preproc`/`expand-sweep` emit the
  mutated/expanded `TestConfig` in `ctx`, not via hidden global mutation.
- **`keyed_join` cannot hold a persistent config port** (it joins every port by key). That's
  why `sim_cmd = {key, seed, log, err, randseed_path}` is a dedicated keyed payload from
  `sim-build` to the `randseed` join rather than a persistent config port. `simv` needs no
  port at all — it is set by `build-compile-cmd` and carried in `ctx`.
- **`discover-config-file` is reusable for the harness's own config.** The harness already
  locates `rtl_comrade_config.yaml` by walking up the tree — worth sharing one implementation.

## Process note

This plan was developed without reading `test-implementation/` (your existing plan) or
`graphs/graph3.yaml` (the graph already wired to the `test` command), so it is independent
and comparable to yours.

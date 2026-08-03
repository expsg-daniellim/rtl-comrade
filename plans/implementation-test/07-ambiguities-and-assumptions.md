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

2. **Correlation strategy** (revised — split-edge model; supersedes the original
   single-envelope draft). Per-test/per-run data rides as
   separate keyed edges (`test` bare and self-keyed; `model`/`simv`/`run_id`/`seed`/`timeout`/
   `filelist` as `KeyedValue` envelopes; `command`/`proc`/`randseed`/`randseed_done` as cohesive
   messages), each carrying the correlation `key`, so every node consuming ≥2 keyed edges is a
   `keyed_join` — not just `cc-int`/`randseed`. `write-randseed` is a 2-port `keyed_join`
   (`randseed` + a `proc` completion gate) and a **side-effect leaf**: it builds no result
   record; the post-sim region consumes `test` + `proc` directly. Only the single-keyed-input
   nodes (`filter`, `load-model`) stay `default`; config singletons reach the joins as
   `persistent_inputs`. Full detail in [02](02-payload-conventions.md),
   [04](04-pipeline-and-contracts.md), [06](06-graph-yaml.md).

3. **~~`fan-in-results` module + `any` contract for terminal fan-in~~ — superseded by TODO #15
   (item 27).** Earlier drafts re-converged the 13 terminal outcomes through a
   `fan-in-results` relay + `any` contract feeding `aggregate-results`. The TODO #15 redesign
   removed both nodes. Since spec [10d](specs/10d-summarise-results.md) the summary is back in the
   graph as the `results-summary` node: the 13 result ports are **wired** to it and the `any`
   contract (spec 02) is its fan-in — but the old `fan-in-results` relay + `aggregate-results` pair
   is **not** reintroduced (the contract fans straight into the accumulating sink). See item 27 and
   [05](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node).

4. **`run-process` redirects to caller-supplied files; emits paths.** stdout/stderr go
   straight to files named in `command`, so partial output survives a SIGQUIT and memory
   stays bounded regardless of log size. It carries an opaque correlation `key` (never read
   or branched on) so downstream `keyed_join` can match `proc` to the per-test edges by key. Used as two node
   instances (compile/sim).

5. **Post-sim trio (atomic split).** `write-randseed` writes `.randseed` and holds the
   sim-side `keyed_join`; `link-latest` forces the `test.*` symlinks (distinct functionality
   per directive); `interpret-sim` is pure routing on `proc.rc is None`. The `.log`/`.err` files
   are written by `run-process` itself — there is no separate "logs writer" module.

6. **Post-parse split.** `route-post` (classifies on `test.uvm`) + `parse-log`
   (`VlogPost`) + `parse-uvm-log` (`UvmVlogPost`). The two parsers are atomic and
   independently reusable; the uvm/plain decision lives in one router.

7. **List-mode split.** `route-list-mode` + `list-test-names` + a pure `select-tests`.
   `--list` is routing off the main line, not an `if list:` inside `select-tests`.

8. **`load-model` is lazy** (per-test, after `filter`, but before the `sweep`/`preproc` hooks).
   Accepted as a behavioural upgrade — skipped tests no longer pay for (or fail on) their
   `models.yaml`. It sits ahead of the hooks (not just before `write-filelist`) so each hook can
   expose the resolved `ModelConfig` to its script as `test_cfg.model`, matching rtl_buddy's
   suite-load resolution order (`config/suite.py:46` → `test.py:320-323`, before sweep/preproc).

9. **No scheduling in modules.** Branches are named output ports; correlation lives in
   `keyed_join`; persistent config lives in the `default` contract. Terminal re-convergence
   is the `any` contract's fan-in into the `results-summary` node (item 27) — the 13 terminal
   ports are wired there. No envelope, no passthrough guards, no `result` field on the
   main line.

10. **Exit code via logging** (revised by TODO #15, item 27). The exit code is driven by
    `log.error` at **two layers**: each failure terminal's **per-case** event at origin, plus
    the consolidated `log.error("test_failures", count=…)` that `results-summary.finalise()`
    emits on any FAIL row. Either sets `handler.failure` → harness exits 1 (reproducing
    rtl_buddy's OR-accumulated exit code). A PASS / SKIP outcome is recorded by its `TestResult`
    only — a `TestResult`-producing node logs solely the errors it encounters, so it contributes
    nothing. **`early-stop` is the one NA that does not contribute**: `EarlyStopResults` is NA, but a
    user-requested stop is not a failure, so `early-stop-gate` emits no `log.error`
    (exit 0), and an early-stop NA is not a FAIL row so the consolidated check skips it — a
    deliberate divergence from rtl_buddy, which exits 1 on `--early-stop` (recorded under "Notable
    divergences"). A genuine NA from `parse-log`/`parse-uvm-log` still logs `log.error`
    (`parse_log_unknown`) → exit 1. CRITICAL is reserved for fatal config
    errors (matching `logger.critical` → `typer.Abort`). Per-test config-domain failures
    (`load-model` missing/malformed, `write-filelist` source-not-found, `expand-sweep` exec
    crash, `run-preproc` exec crash, `resolve-seed` REPLAY missing/malformed `.randseed`)
    emit on a `fail` output port (wired to `results-summary`) and `log.error` once at emission
    under their per-case event name.
    `run-process` subprocess-launch failure (binary not on PATH, permission denied) is
    `log.fatal` (system-wide, not per-test). Parse-machinery exceptions distinct from FAIL
    classification are deferred pending item 15. Full per-site table in
    [05 — Log idioms](05-branching-and-results.md#log-idioms-per-failure-site).

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
    [spec 09](idx-09-post.md):
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
    single ready port; end when all end). `aggregate-results` retained `run(self, result)`
    with `default`. No harness change required. **Superseded by TODO #15 (item 27):** both
    `fan-in-results` and `aggregate-results` were removed; the `any` contract (spec
    [02](specs/02-any-contract-and-fan-in.md)) is now wired as the `results-summary` fan-in
    (spec [10d](specs/10d-summarise-results.md)), without the relay/sink pair. (Number kept at 19 to
    preserve cross-references.)

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

22. **`keyed_join` payload delivery** (settled 2026-06-02). Modules at the `keyed_join` nodes
    receive their keyed port payloads unwrapped — no `Payload`
    wrapper. E.g. `cc-int` receives `test`, `simv`, and `proc`; `write-randseed` receives
    `randseed` and `proc`. Settled by `docs/modules/implementation.md` Runtime Call Model:
    "the harness unwraps the payload objects to raw values" and "modules receive raw
    values, not `Payload` wrappers." The unwrap happens at `src/rtl_comrade/node.py:281`
    before `module.run(**inputs)` and is contract-agnostic, so `keyed_join` delivers raw
    dicts (matching the example in `docs/contracts/keyed_join.md`). No alternative payload
    shape needed. (Number kept at 22 to preserve cross-references — sits in Settled
    despite being numerically out of order.)

24. **Artefact base for `test`/`randtest`: the CWD, via a dedicated `work-dir` node** (settled
    2026-06-02; revised through Option B to the final split 2026-06-22). rtl_buddy splits this policy:
    `do_cmd_test` never `chdir`s and works in — writes to — the ambient CWD, while `do_rtl_regression`
    `os.chdir`s into each suite's directory (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:404`). **Design
    history (two rejected drafts):** (a) a `check-suite-cwd` node first *enforced* a user-driven
    convention with a CWD-mismatch `log.fatal` — rejected, it forbids the conventional
    `-c <dir>/tests.yaml`; (b) "Option B" then had a `resolve-suite-config` node emit
    `work_dir = resolved.parent` (the config's directory), giving `test` the *regression* policy —
    rejected because it contradicts "run here, output here" (it relocates output to the config's dir)
    and conflated two unrelated concerns (resolving a config path vs. providing the artefact base).
    **Final:** the artefact base is the **CWD**, provided by a zero-input
    [`work-dir`](specs/04f-work-dir.md) node (`work_dir = Path.cwd().resolve()`) — faithful to
    `do_cmd_test`. `-c <dir>/tests.yaml` only *locates* the config; artefacts stay in CWD and relative
    config paths are CWD-relative (conventional, the user's responsibility) — no auto-relocation, no
    CWD-mismatch abort. The path resolution **and** the missing-file failure fold into
    [`parse-suite-config`](specs/04h-parse-suite-config.md) (it opens the file and derives
    `suite_dir = path.parent` anyway), so there is no separate resolve node. The leaf modules root on the
    provided `work_dir` rather than reading the ambient CWD: `run-process` launches with `cwd=work_dir`
    (concurrency-safe per-`exec` equivalent of regression's process-wide `chdir`; spec
    [03](specs/03-run-process.md)), `write-filelist` roots the `.f` contents on it
    ([06b](specs/06b-write-filelist.md)), `write-randseed` reads `HierInstanceSeed.txt` from it
    ([08d](specs/08d-write-randseed.md)), and `link-latest` places the `test.*` symlinks under it
    ([08e](specs/08e-link-latest.md)). For `test`/`randtest` `work_dir == CWD`, so those four are
    identity vs rtl_buddy; they are load-bearing for **regression**, which wires **no** `work-dir` node
    and instead feeds the same `work_dir` ports a per-suite `suite_dir` (`parse-suite-config`'s
    `path.parent`) — the per-`exec` form of `do_rtl_regression`'s per-suite `chdir`.

25. **`.`-prepend to `$PATH`: dedicated `prepend-cwd-path` setup node** (settled
    2026-06-02). `rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102` mutates
    `os.environ["PATH"]` once at CLI bootstrap so a CWD-local simulator (`simv`,
    `verilator`) is discoverable. This plan reproduces this as an explicit graph node:
    [`prepend-cwd-path`](03-module-catalog.md) (spec
    [04](idx-04-setup.md)), a zero-input `unit` setup node that performs
    the same idempotent prepend and emits a `bool` sentinel on `default`.
    `run-process` declares a generic input `env_ready:bool = True`; the graph wires
    `prepend-path → cc-run.env_ready` and `prepend-path → sim-run.env_ready` **directly**
    (no relay through `ensure-logs`), marks each edge **`required: true`**
    (`docs/harness_configs/graph.md`), **and** lists `env_ready` in each `run-process`'s
    `persistent_inputs`. The two markings together reproduce the `logs_dir` pattern: `required`
    has the contract ignore the module's Python default, so the **first** invocation is a blocking
    required port — pinning the PATH mutation strictly upstream of the first subprocess — while
    `persistent` caches that one token and replays it on every later invocation (`prepend-path`, a
    `unit` node, emits `env_ready` once, whereas `cc-run`/`sim-run` run once per test). The Python
    default `True` is retained so the module stays unit-testable in isolation (tests pass
    `env_ready=True`); `required`/`persistent` are per-wiring properties, so both that and the
    blocking ordering hold at once. The input name is deliberately generic so any
    future env-setup node can join the same sequencing surface. **Considered and
    rejected**: (a) doing the mutation inside `run-process` (per-call, mutates
    process-wide state in the inner loop, widens the workhorse's responsibility);
    (b) doing it inside `resolve-builder` (widens a config-resolution module with
    env-policy concerns; no natural successor if future env-setup nodes are added).
    Wired in all three graphs (test/randtest/regression) — the mutation is harmless
    where unused and load-bearing where the simulator binary sits in CWD. Supersedes
    the "Implementation notes" entry of the same name below (now removed).

26. **Artefact-location provenance, `logs/` ownership, lifecycle, and `--logs-dir`**
    (settled 2026-06-02; **provenance centralised 2026-06-16**). Artefact location is
    decided in **one** place and flows as data — the leaf writers do not re-derive it from the
    ambient CWD. The zero-input [`work-dir`](03-module-catalog.md) node emits the artefact base
    `work_dir = Path.cwd().resolve()`; [`ensure-logs-dir`](03-module-catalog.md) (spec [04](idx-04-setup.md),
    a `unit` node) roots the artefact directory on it — `(Path(work_dir) /
    logs_dir).mkdir(parents=True, exist_ok=True)` once at startup; no other module calls `mkdir`
    — and **emits the resolved directory `Path`** on its `logs_dir` port. That `Path` fans out
    as a persistent input to the composers `build-compile-cmd` / `build-sim-cmd` / `resolve-seed`,
    which **join filenames onto it** and never touch the process CWD. So the rtl_buddy
    "everything is CWD-relative" assumption is fully replaced by the `work_dir` provider: every leaf
    *path* roots on `work_dir`, and `run-process` roots the subprocess *`cwd`* on it (spec
    [03](specs/03-run-process.md)), so relocating artefacts (a future `--work-dir`, or regression's
    per-suite root) is a change to the `work-dir` provider alone — the leaf modules never read the
    ambient CWD (see Settled item 24). **Default location** is `<work_dir>/logs` — `work_dir` is the
    CWD for `test`/`randtest` (and the per-suite `suite_dir` for regression), giving parity with
    `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` (where `VlogSim.__init__` lazily
    `makedirs`'s a hard-coded `"logs"` literal per test). This plan lifts that into one setup node so
    (a) no downstream writer needs `mkdir`, (b) the directory is materialised once per invocation
    rather than per `VlogSim`, (c) the subdir name is overridable, and (d) the *location* is a
    single data source rather than a leaf-level convention. **`-L/--logs-dir`** (default `"logs"`,
    the subdirectory **name**) is a small Notable divergence from rtl_buddy (which has no override)
    — it is a CLI edge to `ensure-logs-dir` only. `write-randseed` does not consume `logs_dir` —
    `build-sim-cmd` emits `randseed_path` on the `randseed` message so the `keyed_join` receives it as a
    dedicated keyed port (no persistent config port on keyed_join — see Implementation notes).
    **Sequencing**: `ensure-logs-dir` carries **no `env_ready` token** (revised; an earlier draft
    relayed one `prepend-path → ensure-logs → cc-run/sim-run`). The two env-setup orderings are now
    independent data edges: the PATH prepend is sequenced by `prepend-path → cc-run/sim-run.env_ready`
    (`required: true`, item 25) directly, and the `logs/` `mkdir` is sequenced by the `logs_dir`
    **data** edge — `ensure-logs-dir` `mkdir`s *before* emitting `logs_dir`, and the composers take
    `logs_dir` as a first-run-required input (no Python default), so they block on it before building
    a command and the directory provably exists before any subprocess redirects into it. No relay
    token is needed for the `mkdir`, which restores `ensure-logs-dir`'s atomicity (it depends only on
    `work_dir`, which it reads). `ensure-logs` takes `work_dir` from the `work-dir` node as **load-bearing**
    data (read to root the directory, so a missing edge fails edge-validation — superseding the
    former ordering-only `_cwd` token, whose defaulted-port exemption per item 21 could silently
    skip the guard).
    **Lifecycle**: never auto-cleaned (parity); user owns purging. **Concurrency**: filenames
    within `logs/` are uniquely keyed by `<test_name>[_NNNN]` (sweep + run-id), so no
    within-directory collisions even when the [item 17](07-ambiguities-and-assumptions.md) interim
    shim is in effect. Wired in `test`/`randtest` only — `regression`'s per-suite `chdir` feeds a
    different `work_dir` to the same node, a bootstrap that lives in [08](08-sibling-graphs.md).
    The CWD-relative half of the "CWD assumptions preserved" Implementation notes entry below is
    now explicit, not silent.

27. **`git-status` recorded + summary returned to the graph** (settled 2026-06-10; **further
    revised 2026-06-25**; resolves TODO #15).

    > **Superseded in part (spec [10d](specs/10d-summarise-results.md), 2026-06-25).** The summary
    > **returned to the graph** as the in-graph `results-summary` node: the 13 result ports are
    > **wired** there via the `any` contract, each terminal logs a **per-case** event (no generic
    > `test_result`), and `results-summary.finalise()` renders the table *and* emits the
    > consolidated `log.error("test_failures", …)` exit signal. The `SummaryProcessor` logging
    > plugin described below is retired to dormant infra ([10c](specs/10c-summary-handler.md)). The
    > `git-status` decision stands unchanged. The historical TODO #15 record follows.

    Decision: **include** git state, as a logging concern, not a
    graph-routed payload. A new [`git-status`](03-module-catalog.md) zero-input setup node calls
    `log.info("git_state", branch=..., sha=..., dirty=...)` once. The results summary is no
    longer produced by a graph sink: `fan-in-results` and `aggregate-results` are **removed**,
    the 13 result ports are left **unwired**, each terminal node calls
    `log.info("test_result", ...)` at emission, and a per-graph **`SummaryProcessor`** (a
    stateful structlog processor in `graphs/log/summary.py` — **not** a `logging.Handler`)
    accumulates the `test_result` rows (**results only**) and renders the table in its
    `finalise()` teardown hook. The processor both collects each row and raises `DropEvent` to
    suppress its per-event console line, so no separate `drop_summary_events` processor is
    needed. `git_state` is **not** collected by the processor — it falls through to the console
    and prints at run start. The exit code is driven solely by per-emission `log.error`
    (item 10). Rationale, sketches, and the CRITICAL path in
    [05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node);
    spec in [10](idx-10-control-aggregate.md).

    **Plugin form revised 2026-06-11 (processor, not handler).** The plugin was first specified
    as a `SummaryHandler` (`logging.Handler`) + a paired `drop_summary_events` processor; it is now
    a single `SummaryProcessor`. A processor is the right kind: processor classes hold state, a
    processor sits before `ConsoleRenderer` to intercept-and-accumulate result events, and
    `DropEvent` — a processor-only mechanism — suppresses their per-event lines in the *same*
    object, removing the second piece. The per-run finalisation hook covers processors:
    `App.cleanup` finalises the run's processors (then handlers), duck-typed, before the failure
    check and not on a `CRITICAL` exit (`docs/logger/implementation.md:95-99`, timing at
    `:165-167`). The plugin's `finalise()` renders the table.
    **Knock-on:** supersedes items 3 and
    19; revises items 9 and 10. It also disturbed the interim parallel-safety shim (whose lock
    *release* lived on the now-deleted `fan-in` node) — **TODO #30** resolved that by removing
    the shim entirely in favour of per-tag artefact naming (see Deferred item 17).

## Deferred (KIV)

17. **Concurrency / shared CWD paths** — *deferred pending an upstream rtl_buddy change* that
    runs each compile and sim command in its own subdirectory. This is the **reference fix**:
    its per-invocation working directories isolate *every* CWD-relative artefact at once
    (`run.f`, `obj_dir_<tag>/`, `simv`, `test.*` symlinks, `rtl_buddy.log`, and anything the
    tools write into CWD). It remains on the books even after the interim mitigation below,
    which is only a graph-local shadow of it. Keep `run-process` and the sim-side nodes ready
    to honour per-invocation working dirs.

    **Interim posture (settled 2026-05-31; revised 2026-06-05; shim removed → per-tag naming
    2026-06-10).** The earlier interim design serialised the compile/sim region with a
    process-wide `asyncio.Lock` (`serial_acquire` on `write-filelist` + `any.release_lock` on
    `fan-in`). That shim was **removed** (TODO #30): it bought correctness but no parallelism,
    and TODO #15 deleted its release node. **Replaced by per-tag artefact naming (option B):**
    `write-filelist` writes `run.{test_tag}.f` (the one shared filename the graph fully
    controls); `obj_dir_<tag>/`, the verilator `simv`, and the `logs/` paths were already
    per-tag. So concurrent tests no longer collide on those, with no lock and no loss of
    concurrency. **Residual covered only by this item's reference fix:** the non-verilator `simv`
    (a fixed `builder_cfg.get_simv()` name the graph can't freely redirect) and any tool-internal
    fixed-name CWD write are **corrupting** — a concurrent multi-test run on a fixed-`simv` builder
    can overwrite one test's binary with another's and **silently** report wrong results (rc 0,
    green summary); the `test.*` "latest" symlinks race too but are benign (last-writer-wins
    pointers to per-tag targets). There is **no built-in serialisation** (the lock shim was removed
    by TODO #30 and not replaced), so until this item is ported into rtl_comrade the only interim
    workaround is **operational**: run such suites one test per invocation. Mechanism, the per-tag table, and the residual list in
    [05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
    The per-tag naming is itself **temporary** — superseded (not just complemented) when this
    item lands.

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
    with `_TIMEOUT_GRACE_S` SIGKILL escalation, `rc = None` as the timeout indicator
    (replacing rtl_buddy's `4444` sentinel), and explicit cancellation cleanup under `asyncio.shield`. **What
    remains to verify empirically** before the module is built: that the default
    `ThreadedChildWatcher` (Python 3.8+) reaps without explicit `waitpid`; that
    `os.killpg` race-with-already-exited (`ProcessLookupError`) actually surfaces under
    real load (not just contrived tests); that `asyncio.wait_for`'s inner cancellation
    of `proc.wait()` does not interfere with our subsequent `proc.wait()` reap. This plan
    deliberately departs from rtl_buddy on (i) signalling the full process group rather
    than just the leader and (ii) adding SIGKILL escalation — record both under
    "Notable divergences" when implementation lands.

## Notable divergences from rtl_buddy

- **`--early-stop` exits 0, not 1** (settled 10, R2). `rtl_buddy`'s `EarlyStopResults` is NA, and
  `exit_code |= 0 if is_pass() else 1` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:206`;
  `EarlyStopResults` at `runner/test_results.py:53-60`) makes `rtl_buddy test --early-stop <phase>`
  exit **1**. This plan treats a user-requested stop as a deliberate, successful early exit, not a
  failure: `early-stop-gate` emits no `log.error` (a user-requested stop is not a
  failure, and an NA row is not a FAIL row so the consolidated check skips it too), so the run exits **0**. The per-test `NA` verdict is unchanged, but the `desc` also diverges:
  `early-stop-gate` emits `"Stopped early at <phase>"` using the phase token (`pre`/`comp`/`sim`),
  whereas rtl_buddy emits `"Stopped early at preproc"`/`"…compile"`/`"…sim"`
  (`runner/test_runner.py:60,68,76`) — so the `desc` matches only for `sim` and diverges for
  `pre`/`comp`. Both the exit code and the `pre`/`comp` `desc` wording are deliberate deltas.
  Genuine NA verdicts from
  `parse-log`/`parse-uvm-log` are unaffected and still exit 1. See [02 table](02-payload-conventions.md#testresult-values-used-at-the-result-ports),
  [05 — Result aggregation](05-branching-and-results.md#result-aggregation-and-exit-code), and
  [spec 10a](specs/10a-early-stop-gate.md).
- **Verible config dropped; builder resolution re-homed** (R3). rtl_buddy's `RootConfig`
  (`config/root.py:50-231`) loads `cfg-verible` into `VeribleConfig`s and resolves the active
  builder + verible *inside* `platform.initialise` during platform selection. This plan (a) drops
  verible entirely — `VeribleConfigFile`/`VeribleConfig` are not ported, and the `cfg-verible`
  (root) / `verible` (per-platform) keys are left **unparsed** (pyserde ignores unknown keys, so
  files still load drop-in); and (b) keeps the builders dict (`rtl_builder_cfgs`) on a thin
  runtime `RootConfig` and resolves the builder in a dedicated node — `resolve-builder` reads
  `root_cfg.rtl_builder_cfgs` keyed by `platform_cfg.builder` (CLI `--builder` override wins),
  not `platform.initialise`. rtl_buddy's resolved runtime platform object (its `PlatformConfig`, returned by `platform.initialise`) is therefore never built — the raw `PlatformConfig` rides the edge directly. See
  [spec 01 — `root.py` schema](specs/01-shared-schema.md#rootpy-schema-detailed) and
  [04e](specs/04e-resolve-builder.md).
- **`select-platform` is first-match, not last-match.** rtl_buddy iterates every platform with
  no `break` (`config/root.py:111-115`), so when two platforms share a `uname` the *last*
  declared one wins. This plan's [`select-platform`](specs/04d-select-platform.md) returns on the
  *first* match. Overlapping `unames` are a misconfiguration, so the choice is deliberate;
  recorded here so the parity claim is explicit. Single-platform-per-`uname` configs (the norm)
  are unaffected.
- **`load-model` is lazy and off-object** (settled 8) — broken `models.yaml` in a skipped test no
  longer errors early. Departs from rtl_buddy's eager load inside `TestConfigFile.initialise`
  (`rtl_buddy/src/rtl_buddy/config/test.py:320-323`, which calls `ModelConfigLoader.get_model`
  while building every `TestConfig`). The resolved `ModelConfig` is **not** stored on `TestConfig`
  (the `model` field holds only the name string — spec [01b](specs/01b-suite-schema.md)): `load-model`
  emits the resolved object on its own `model` keyed edge, which rides through `sweep`/`preproc`/`gate-pre`
  (each `keyed_join`s it; the hooks also read its value to expose as `test_cfg.model` to their scripts)
  to `write-filelist`, where it is consumed (specs [05e](specs/05e-load-model.md)/[05f](specs/05f-expand-sweep.md)/[06a](specs/06a-run-preproc.md)/[06b](specs/06b-write-filelist.md)).
  This keeps `TestConfig` from ever being in a "resolved model not yet loaded" state, consistent with how
  `filelist`/`simv`/`seed`/`timeout` already flow as their own edges rather than as test fields.
- **Compile output is persisted to files** (settled 12) as a side effect of the redirect.
  Departs from rtl_buddy's in-memory capture `subprocess.run(run_cmd, capture_output=True)`
  (`rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:163`); this plan redirects stdout/stderr to the
  `command` paths in `run-process` instead.
- **Concurrency is structurally available** (deferred 17) — pending the upstream rtl_buddy
  per-invocation-subdir change (the reference fix). **Interim**: artefacts the graph controls
  are named **per-tag** (`write-filelist` writes `run.{test_tag}.f`; `obj_dir`/verilator-`simv`/
  logs already per-tag), so the region runs concurrently without collisions and without a lock.
  The earlier `serial_acquire`/`any.release_lock` lock shim was **removed** (TODO #30). Residual
  shared-CWD artefacts (non-verilator `simv`, `test.*` symlinks, tool-internal files) remain for
  item 17 (see [05 — Interim CWD-collision posture](05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming)).
- **`git-status` is recorded as a logging event** (settled 27) — this plan includes git-state
  capture (rtl_buddy's `show_git_rev` at `rtl_buddy/src/rtl_buddy/rtl_buddy.py:500-522`) but
  routes it through `log.info("git_state")`, which falls through to the console (it is not a
  terminal result, so it does not reach `results-summary`), not through the graph. The summary
  **results** table is rendered by the in-graph `results-summary` node's `finalise()` (spec
  [10d](specs/10d-summarise-results.md); reproducing the `do_cmd_test` print loop at
  `rtl_buddy.py:203-207`), fed by the `any` contract — not a `fan-in-results`/`aggregate-results`
  pair.
- **`postproc_path` not executed** (settled 14) — parity with rtl_buddy, which loads
  `postproc` (`config/test.py:254-264`, `get_postproc_path`) but never runs it (no caller in
  `VlogSim.post`, `tools/vlog_sim.py:283-300`).
- **`VlogPost` quirks corrected in `ParseLogMod`** (settled 15) — word boundary after
  `PASS`/`FAIL`, FAIL wins over PASS when both appear, safe desc when `ERR:`/`FAT:` is
  absent. Departs from `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:23-45` (PASS overrides
  FAIL at `:42-43`; the `match_err.group(2)` crash at `:41` when FAIL has no `ERR:`).
  `ParseUvmLogMod` unaffected. See Settled item 15.
- **`--debug`/`--color` flags not exposed** (settled 11) — logging owned by harness
  `--level`. Drops rtl_buddy's `root_options` flags at `rtl_buddy/src/rtl_buddy/rtl_buddy.py:116-117`.
- **`-L/--logs-dir` is a new CLI override + centralised artefact-location provenance**
  (settled 26; centralised 2026-06-16). `rtl_buddy` hard-codes `"logs"`
  (`tools/vlog_sim.py:55`) and every tool composes paths relative to the ambient CWD; this plan
  keeps the same default but (a) accepts a user-supplied subdir **name**, and (b) decides the
  artefact *location* once — the zero-input `work-dir` node emits `work_dir` (= CWD), `ensure-logs-dir` roots `logs/`
  on it and emits the resolved directory `Path`. The composition sites (`build-compile-cmd`,
  `build-sim-cmd`, `resolve-seed` REPLAY) take that resolved `Path` as a persistent input and
  join filenames onto it — they no longer carry the CWD-relative assumption. This deliberately
  departs from rtl_buddy's leaf-level "everything is CWD-relative" model so relocating artefacts
  is a one-node change.
- **Per-test config-domain failures route as per-test FAIL, not `logger.critical`**
  (settled 10). `load-model`, `write-filelist`, `expand-sweep`, `run-preproc`, and
  `resolve-seed` (REPLAY) emit on a new `fail` port with `log.error` instead of aborting
  the whole run. rtl_buddy `logger.critical`s on preproc-script and sweep-script crashes
  (`vlog_sim.py:134-137`, `rtl_buddy.py:279-281`); this plan continues running other tests.
  REPLAY-missing matches rtl_buddy's per-test FAIL **verdict** via `log.error`
  (`vlog_sim.py:200-213`), but with an **artifact divergence**: rtl_buddy additionally writes a
  FAIL stub `<test>.log`/`.err` and forces the `test.log`/`test.err` symlinks before returning
  (`vlog_sim.py:204-212`), whereas this plan's `resolve-seed` routes the `fail` `result` *before*
  the sim/log/symlink steps run, so no stub log/err or symlinks are produced for a replay-fail.
  The verdict matches; the on-disk artifacts do not.

## Implementation notes

- **`--early-stop` phase ordering**: `pre < comp < sim < post`; mirror rtl_buddy's `RunDepth`.
  Each `early-stop-gate` compares against this ordering.
- **Tags have no manifest field.** `pre/compile/sim/post` are documentation labels only;
  first-class tags would need a manifest + loader extension.
- **Config objects cross edges as live Python objects** (`RootConfig`, `TestConfig`, …). Fine
  for asyncio; would need to be picklable only if the harness ever went multiprocess.
- **CWD assumptions — artefact location fully centralised on `work_dir`.** `root_config.yaml`
  discovery still walks up from CWD. Everything else now roots on the `work_dir` provider
  (the zero-input `work-dir` node, = CWD for test/randtest): `ensure-logs-dir` roots `logs/`, `write-filelist`
  roots both the `run.<tag>.f` filename **and its contents**, `build-compile-cmd` roots `obj_dir_<tag>/`,
  `write-randseed` reads `HierInstanceSeed.txt` from it, `link-latest` places the `test.*` symlinks under
  it, and `run-process` launches every subprocess with `cwd=work_dir` so tool-internal scratch lands there
  too (Settled 24/26). So the user is **not required** to `cd` into the suite dir — `-c <dir>/tests.yaml`
  works from anywhere; the conventional `cd <suite> && rtl-comrade test` simply makes `work_dir == CWD`.
  The residual tracked under [item 17](07-ambiguities-and-assumptions.md) is **concurrency collision**
  (the fixed non-verilator `simv` name, the shared `test.*` pointer names), not CWD-relativity.
  `regression`'s per-suite `chdir` feeds a different `work_dir` to the same providers.
- **`exec`'d preproc/sweep scripts reproduced as-is.** `run-preproc`/`expand-sweep` emit the
  mutated/expanded `TestConfig` on the `test` edge, not via hidden global mutation.
- **`keyed_join` cannot hold a persistent config port** (it joins every port by key). That's
  why the per-run seed / randseed-path / argv ride the dedicated `randseed` message from
  `build-sim-cmd` to the `write-randseed` join rather than a persistent config port. `simv`
  rides its own `KeyedValue[str]` edge, born at `build-compile-cmd` and joined downstream by key.

## Process note

This plan was developed without reading `test-implementation/` (your existing plan) or
`graphs/graph3.yaml` (the graph already wired to the `test` command), so it is independent
and comparable to yours.

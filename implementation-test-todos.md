# implementation-test todos

Todos for bringing the `implementation-test/` plan to a buildable, internally consistent state. Items are grouped into three sections by priority:

- **Design-level** — open questions, unresolved decisions, and structural gaps that must be settled *before* per-spec polish is meaningful. Most of these correspond to items in `implementation-test/07-ambiguities-and-assumptions.md` under "Open", "Deferred (KIV)", and "To verify against the framework before building"; cross-references appear inline as `07` item *N*.
- **Spec polish** — patterns that need to be applied to each `specs/` ticket so that an implementer can build a module from the spec alone, without flipping between catalog, design files, and rtl_buddy source.
- **Cosmetic** — small structural improvements; not blocking.

Items are numbered globally for cross-referencing (e.g., "see TODO #5"). The order within each section reflects rough priority but is not load-bearing — items in the same section can be picked up in parallel where dependencies allow.

> **Note on file:line citations.** All file/line references in this document are anchored to commit `9308c86` at todo-creation time. Re-verify line numbers against the current state of the source files before acting on a citation.

## Design-level — must resolve before building

### 1. Enumerate failure modes — and resolve open questions sitting in build tickets

**Status: Resolved (2026-05-31).** Step 1 (hedge-phrase scan across `specs/`) returns 0
matches after the `08` REPLAY edit. Step 2 (per-module failure audit: exception classes,
emission shape, log idiom) is captured in each module's spec via inline
`**Failure handling:**` blocks across specs 03–10; the log-idiom dimension is centralised
in [`05-branching-and-results.md` — Log idioms per failure site](implementation-test/05-branching-and-results.md#log-idioms-per-failure-site).
Step 3 (decide / promote each open question) is vacuous given step 1's empty result;
the one example originally cited is resolved (see TODO #2). Step 4 (re-read each spec
end-to-end) is implicit in the per-module annotation pass. New Notable divergences from
rtl_buddy (per-test FAIL routing for preproc/sweep/load-model/write-filelist crashes)
are recorded in `07-ambiguities-and-assumptions.md`.

Several `specs/` tickets contain unresolved design questions phrased *as* spec prose. The clearest example is `specs/08-sim-cycle-modules.md:24-26` for `ResolveSeedMod`'s REPLAY-missing path:

> "on missing/invalid file, emit a `result` envelope with `SimTimeoutResults`-style FAIL? — actually per [03] writes a FAIL stub log + symlinks (verify against rtl_buddy `VlogSim.execute` REPLAY-missing path)."

A build ticket should never contain a question the implementer cannot answer from the ticket alone. This is upstream of every other todo in this file — none of the per-spec polish below is meaningful until specs are actually answerable.

The specific `ResolveSeedMod` REPLAY-missing example cited above is now resolved (see TODO #2) and the spec file (`specs/08-sim-cycle-modules.md:19-27`) has been updated. The broader audit — scanning every `specs/` file for hedge phrases — remains open.

#### Concrete steps

1. Scan every `specs/` file for: question marks, "TBD", "verify against", "actually" (often introduces a contradiction), and similar hedge phrases. Treat each hit as a candidate open question.
2. Audit each module's failure paths explicitly. For every reachable failure (missing file, parse error, subprocess non-zero rc, timeout, validation mismatch), the spec must name:
   - the exception class(es) the implementer catches,
   - the emission shape (output port + payload type), or the log idiom (see TODO #2 on `log.fatal`/`log.error`).
3. For each open question found in step 1, take exactly one of three actions:
   - Decide it now and write the resolution into the spec.
   - Promote to `07-ambiguities-and-assumptions.md` under "Open" with an owner and a deadline.
   - Promote to "Deferred (KIV)" with an explicit reason if the answer depends on upstream work.
4. Re-read each spec end-to-end and ask: "If I followed only this file, do I know what to build?" Anything unanswerable goes back onto the resolution list.

#### Acceptance check

No `specs/` file contains a question mark or hedge phrase in `Deliverables` or `Acceptance criteria`. Any remaining open items carry an explicit `[open: see 07-...]` tag pointing at the corresponding entry in `07-ambiguities-and-assumptions.md`.

### 2. Integrate graph failures with `log.fatal` / `log.error`

**Status: Resolved (2026-05-31).** Per-site decisions and the topology consequences live in
[`implementation-test/05-branching-and-results.md` — Log idioms per failure site](implementation-test/05-branching-and-results.md#log-idioms-per-failure-site).
Each affected module entry in `implementation-test/03-module-catalog.md` carries a one-line
`**Log idiom:**` pointer. Downstream edits to row 22 of `04-pipeline-and-contracts.md`,
the edge list in `06-graph-yaml.md`, and Settled item 10 in `07-ambiguities-and-assumptions.md`
followed. Parse-machinery exceptions (distinct from FAIL classification) are still deferred
pending TODO #13 (VlogPost quirks).

The plan states the principle in three places (`00-overview.md:142`, `05-branching-and-results.md:101-113`, `07-ambiguities-and-assumptions.md:57-60`): `aggregate-results.finalise()` calls `log.error` if any row is not `is_pass()`, and `CRITICAL`/`FATAL` is reserved for unrecoverable config errors. Per `docs/invariants.md:20-21`, `ERROR` defers to a non-zero exit and `CRITICAL`/`FATAL` triggers immediate `SystemExit(1)`.

What is missing is a per-site enumeration. Each module and contract that can fail needs an explicit decision recorded — either in its `03-module-catalog.md` entry or in a new section of `05-branching-and-results.md` — answering one of:

- **route via a named port** (failure becomes a `result` payload, joins the merge fan-in, contributes to the `aggregate-results.finalise()` ERROR)
- **`log.error` directly** (deferred non-zero exit, no result row needed)
- **`log.critical` / `log.fatal` directly** (immediate `SystemExit(1)`, no merge involvement)

Sites that need a decision:

- `load-root-config`, `resolve-builder`, `load-testbench`, `parse-suite` setup failures (missing/malformed files, builder not found, testbench not resolved) — likely `CRITICAL`
- `select-tests` when the named test is not in the suite — `CRITICAL` (matches rtl_buddy's `typer.Abort`) or routed via `route-list-mode`?
- `filelist` load failure, `load-model` missing-model, `expand-sweep` exec failure — `CRITICAL` vs port-routed `result`
- `run-process` non-zero rc on compile (`cc-int.fail`), sim timeout (`interpret-sim.timeout`), sim non-zero rc — already routed via named ports, confirm they reach the merge and not `log.error`
- `resolve-seed` REPLAY failure (missing/malformed `.randseed`) — currently undefined (this is the gap called out in the Plan A/B comparison); decide between port-routed `FAIL` `result` (Plan A's choice) and `CRITICAL`
- `interpret-sim-default` and `interpret-sim-uvm` parse failures distinct from FAIL classification — port-routed or `log.error`?
- `early-stop-gate.stop` — `result` payload only, no log call (it's a normal terminal, not a failure)
- `MergeContract` internal scheduling errors — `CRITICAL`

For each site:

1. Pick one of the three idioms above and record it in the module's catalog entry.
2. If `log.error` is used, confirm the harness's deferred-exit mechanism actually fires for the chosen call site (a module's `run()` vs a contract's scheduling code — verify both paths participate in the exit-code contract).
3. Add an acceptance criterion in the corresponding `specs/` ticket: "module X under failure Y produces \<chosen idiom\>" with a test.

Cross-reference: Plan A (`test-implementation/20-summary-and-exit-code.md`) enumerates this per-module for its design. Use it as a checklist when filling out the equivalent for this plan, but do not import Plan A's choices uncritically — the port topology here is different (notably, `aggregate-results` is the only `log.error` site by design, so most failures should be port-routed `result`s rather than direct `log.error` calls).

### 3. Define the interim strategy for parallel runs

**Status: Resolved (2026-05-31).** Posture chosen: option (b), a serialising contract on the
compile/sim region. The hazard is that a concurrent next-test compile would stomp the prior
test's non-graph-routed build artefacts (`obj_dir_<tag>/`, `simv`, `run.f`) before its sim
has consumed them. Posture: `write-filelist` acquires a process-wide `asyncio.Lock` per
(test, sweep-variant); `aggregate-results`' existing `merge` contract releases the same lock
once per delivered terminal payload. Pre-region nodes still parallelise across tests; the
mid-region is atomic per test. Two contract pieces: a new `serial_acquire` contract, and an
extension to the existing `merge` contract (`release_lock` Config field). Both are
**explicitly temporary** and must be removed when upstream `rtl_buddy` per-test artefact
dirs land (see `07` item 17). Scoped to the plain `test` graph (R=1); sibling graphs
(`randtest`, `regression`) need a different release rule and are out of scope here.
Mechanism, constraints, sketch, and cross-links are in
[`05 — Serialising contracts`](implementation-test/05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture);
node-table update in [`04`](implementation-test/04-pipeline-and-contracts.md) rows 7 and 22;
graph + manifest wiring in [`06`](implementation-test/06-graph-yaml.md); cross-link from
[`07`](implementation-test/07-ambiguities-and-assumptions.md) item 17 (kept in Deferred —
the upstream change itself is still deferred).

`07-ambiguities-and-assumptions.md:146` notes `obj_dir`, `logs/`, and CWD-based artefacts are all CWD-relative — same as rtl_buddy. `07` item 17 defers per-invocation subdirs to an upstream rtl_buddy change. But structural concurrency is the design's whole advantage over rtl_buddy, and running two compiles or two sims in parallel will collide on `run.f`, `obj_dir`, `test.*` symlinks, and `rtl_buddy.log`. With no interim plan, the graph is effectively single-threaded.

#### Concrete steps

1. Pick an interim posture, explicitly: (a) wait for the upstream change and document the graph as single-threaded until then; (b) add a serialising contract on the compile/sim chain that enforces one-at-a-time within a suite; or (c) introduce per-key tempdirs at the graph level (e.g., `obj_dir/<key>/`).
2. If (a): add a constraint in `01-cli-and-entry.md` ("workers clamped to 1 until upstream lands"), and record the dependency.
3. If (b) or (c): write a design note and spec for the new contract or tempdir scheme. Identify which modules need to be aware (`link-latest`, `write-randseed`, anything CWD-touching).
4. Cross-link the chosen posture from `07-ambiguities-and-assumptions.md` item 17.

#### Acceptance check

Any reader can answer "what happens if two tests run in parallel?" without the entire answer being "the upstream change."

### 4. Validate the `MergeContract` design before downstream specs depend on it

**Status: Resolved (2026-05-31).** Step 1 (formal description) is captured in
[`05 — Invariants and termination`](implementation-test/05-branching-and-results.md#invariants-and-termination):
state, no-loss invariant, per-port `EndSentinel` handling, drainage order, non-correlating
behaviour, termination rule, and `release_lock` side-effect. Steps 2–3 (stress test +
property-based test) are enumerated as concrete test cases in
[`specs/02-merge-contract.md`](implementation-test/specs/02-merge-contract.md) — including
the multi-done-per-wake and drainage-order cases the original prose only implied. Step 4
(`docs/contracts/index.md` promotion) is added as an acceptance criterion on the same spec,
to be carried out during implementation; the interim `release_lock` field is included in
the entry but flagged as a TODO #30 hook rather than as part of the contract's first-class
surface. The `SerialAcquireContract` + `merge.release_lock` interim shim added by TODO #3
is **not** in scope for TODO #4 — tracked separately in TODO #30.

`05-branching-and-results.md:98-99` identifies `MergeContract` as the only piece of genuine scheduling the design adds. `07` items 19–20 acknowledge that its concurrency safety is asserted, not proven. Eight terminal-result branches converge on `agg` through it (`04-pipeline-and-contracts.md` row 22); if it is wrong, every branch is wrong.

#### Concrete steps

1. Write a formal description: state held across `get()` calls, how `EndSentinel` propagates from each upstream port, behaviour on a key whose branch has already terminated, and the contract's overall termination rule.
2. Add a stress test: concurrent emissions from 8 mock upstreams with overlapping keys; assert no items lost, no duplicates emitted, and termination once all upstreams sent `EndSentinel`.
3. Add a property-based test if feasible: random `(key, port, payload)` interleavings produce a deterministic output set.
4. Once stabilised, document the contract in `docs/contracts/index.md` as a first-class shipped contract — not an `rtl_test`-private artefact.

#### Acceptance check

`MergeContract`'s correctness is supported by enumerated tests and a written invariant, not by intuition.

### 5. Finalise `run-process` async + signal semantics

**Status: Resolved (2026-05-31).** Spec rewritten as
[`specs/03-run-process.md`](implementation-test/specs/03-run-process.md) with an
exhaustive Lifecycle section (states 1–4, including the timeout 3a and cancellation 3b
cleanup paths), a Signal-and-timeout-policy table, an `rc=4444` ownership block, a
Cancellation-behaviour block, four enumerated failure cases (launch failure, external
kill, exit-before-wake, never-reaps), and ten enumerated tests exerciseable against a
slow-sleep bash fake. Two deliberate departures from rtl_buddy: SIGQUIT to the full
process group (not just the leader; rtl_buddy `vlog_sim.py:259` only signals the
leader) and SIGKILL escalation after a `_TIMEOUT_GRACE_S = 5.0 s` window. `timed_out`
is set independently of `rc` (rtl_buddy implicitly uses `rc == 4444`). Catalog sketch
in [`03-module-catalog.md`](implementation-test/03-module-catalog.md) updated to match;
[`07-ambiguities-and-assumptions.md`](implementation-test/07-ambiguities-and-assumptions.md)
item 23 updated with a "what remains to verify empirically" note (design is
finalised but the framework probes still need to run before module implementation).

`07` item 23 flags the SIGQUIT-to-process-group + `rc=4444` + `asyncio.wait_for` interaction as tricky and unfinalised. `run-process` is shared by compile and sim; if its semantics drift, both legs misbehave.

#### Concrete steps

1. Specify the timeout path explicitly: which signal is sent (`SIGTERM`/`SIGQUIT`/`SIGKILL`), to whom (process or process group), with what grace period before escalation.
2. Define the `rc=4444` sentinel: when it appears, what it means, who sets it, who reads it. Match rtl_buddy's convention.
3. Specify `asyncio.wait_for` cancellation cleanup — orphan subprocess handling, file-handle closure for redirected stdout/stderr, partial-output preservation guarantees.
4. Add explicit failure cases to `specs/03-run-process.md`: subprocess killed externally; subprocess exits before `wait_for` schedules its wake-up; subprocess never reaps.

#### Acceptance check

`specs/03-run-process.md` documents the lifecycle from `popen` to either `rc=int` or `rc=4444` with no hand-wave, and is testable against a slow-sleep fake.

### 6. Document framework-verification contingencies

**Status: Resolved (2026-06-02).** All three probes in `specs/00-framework-verification.md`
turned out to be answerable from the harness docs/source, not empirically. Resolutions
recorded in `07-ambiguities-and-assumptions.md` Settled items 19, 21, 22 (numbers kept in
place to preserve cross-references):

- **`**kwargs` port inference (07 item 19)** — `src/rtl_comrade/structure.py:115-119`
  builds ports strictly from `inspect.signature(...).parameters`, so `**kwargs` produces
  one VAR_KEYWORD port, not arbitrary inference. Design pivoted to `MergeContract` M-N
  fan-in with contract-declared input ports (module declares only `result`, contract
  declares the 13 terminal-source inputs via `Config.fan_in`). Depends on a harness
  change called out as a prerequisite in
  [`specs/02-merge-contract.md`](implementation-test/specs/02-merge-contract.md#prerequisite);
  implementation work owned outside this plan.
- **Persistent input with no upstream edge (07 item 21)** — settled by three doc citations
  (`docs/harness/validation.md:39`, `docs/contracts/default.md` step 4,
  `docs/modules/implementation.md`). Default-having ports are exempt from edge validation
  and the default contract falls through to the Python default when nothing has been
  queued. `run_ids = [None]`, `reg_level = None`, `start_level = None` fire as written;
  no constant-emitter or sentinel-edge workaround needed.
- **`keyed_join` payload unwrap (07 item 22)** — settled by `docs/modules/implementation.md`
  Runtime Call Model: the harness unwraps payloads to raw values at `node.py:281` before
  `module.run(**inputs)`. Universal across contracts, so `keyed_join` delivers raw dicts.
  No alternative payload shape needed.

Knock-on edits: `specs/00-framework-verification.md` deleted entirely (the doc-settled
probes were its only content); `specs/README.md` index updated; `specs/01-shared-schema.md`
and `specs/03-run-process.md` lose their "Depends on: spec 00" line; `specs/11-graph-and-manifests.md`
loses its kwargs-fallback note. **TODO #11 is closed by the same evidence** — see its
resolution.

### 7. Pin the interim CWD strategy

**Status: Resolved (2026-06-02).** Posture chosen: user-driven invocation (parity with
`rtl_buddy`, whose `do_cmd_test` never `chdir`s — only `do_rtl_regression` does, at
`rtl_buddy/src/rtl_buddy/rtl_buddy.py:404`), with a new `check-suite-cwd` setup node
enforcing the convention via `log.critical`. The check resolves the CLI `test_config`
against CWD and fails if `(Path.cwd() / test_config).resolve().parent !=
Path.cwd().resolve()` or if the resolved file doesn't exist — catching three
monorepo-mistarget cases (`-c /abs/elsewhere/tests.yaml`, `-c ../sibling/tests.yaml`,
`-c subdir/tests.yaml`) that the existing `parse-suite-config` file-missing check does
not. Wired in `test` and `randtest`; not wired in `regression` (which `chdir`s
per-suite). Spec in [`specs/04-setup-modules.md`](implementation-test/specs/04-setup-modules.md);
catalog entry in [`03-module-catalog.md`](implementation-test/03-module-catalog.md);
node row S4.5 in [`04`](implementation-test/04-pipeline-and-contracts.md); log-idiom
row in [`05`](implementation-test/05-branching-and-results.md#log-idioms-per-failure-site);
graph + manifest in [`06`](implementation-test/06-graph-yaml.md); user-facing convention
in [`01`](implementation-test/01-cli-and-entry.md) under "Where to invoke `rtl-comrade
test` from"; sibling-graph wiring in [`08`](implementation-test/08-sibling-graphs.md);
Settled item 24 + updated "CWD assumptions preserved" implementation note in
[`07`](implementation-test/07-ambiguities-and-assumptions.md).

`08-sibling-graphs.md:135` drops `chdir-suite` "on the assumption" the upstream per-invocation-subdir change lands first. The plain `test` graph already relies on CWD-based artefact placement (`link-latest` writes symlinks "in CWD"; multiple modules write to `logs/...`). Until the upstream change lands, the design silently assumes someone `cd`s into the suite directory before invocation. The CLI entry path does not say so. (See `07-ambiguities-and-assumptions.md` "Implementation notes" — "CWD assumptions preserved" — for the explicit acknowledgement; the deeper concurrency story is `07` item 17.)

#### Concrete steps

1. Decide: does `rtl_comrade test` `cd` automatically to a derived directory (e.g., `<suite_dir>`), or must the user do so before invocation?
2. If automatic: add a small `chdir-suite` module (the one named in the dropped design) and wire it into the test graph, not only the regression sibling.
3. If user-driven: add a startup check that fails fast if CWD is outside the suite directory.
4. Update `01-cli-and-entry.md` to record the convention.

#### Acceptance check

`01-cli-and-entry.md` answers "where do I invoke `rtl_comrade test` from?" without ambiguity.

### 8. Prepend `.` to `$PATH` for CWD-local tool discovery

**Status: Resolved (2026-06-02).** Owner chosen: a new dedicated `prepend-cwd-path`
setup `unit` node (spec [04](implementation-test/specs/04-setup-modules.md), catalog
entry in [03](implementation-test/03-module-catalog.md)), zero-input, that mirrors
`rtl_buddy/src/rtl_buddy/rtl_buddy.py:100-102` and idempotently prepends `.` to
`os.environ["PATH"]`. Sequencing is provided by a generic persistent input
`env_ready:bool = True` added to `run-process`: the graph wires
`prepend-path → cc-run.env_ready` and `prepend-path → sim-run.env_ready` so the
harness's data-dependency ordering pins the PATH mutation strictly upstream of every
subprocess (no race window). The `env_ready` name is deliberately generic so any
future env-setup node joins the same sequencing surface — `run-process` itself stays
ignorant of PATH policy. Considered and rejected: doing the mutation inside
`run-process` (per-call in the inner loop, widens the workhorse) and inside
`resolve-builder` (widens config-resolution with env-policy concerns). Knock-on
edits: catalog entries and provenance row in
[`03`](implementation-test/03-module-catalog.md); node-table row S0 plus `cc-run` /
`sim-run` input lists and the setup narrative in
[`04`](implementation-test/04-pipeline-and-contracts.md); graph node + two
`env_ready` edges + manifest line in
[`06`](implementation-test/06-graph-yaml.md); deliverable + tests + acceptance
criterion in [`specs/04-setup-modules.md`](implementation-test/specs/04-setup-modules.md);
ownership resolution + `env_ready` test bullet in
[`specs/03-run-process.md`](implementation-test/specs/03-run-process.md); sibling-graph
reuse note in [`08`](implementation-test/08-sibling-graphs.md); promotion of the
"Implementation notes" entry to Settled item 25 in
[`07`](implementation-test/07-ambiguities-and-assumptions.md).

`07-ambiguities-and-assumptions.md` "Implementation notes" records that rtl_buddy prepends `.` to `$PATH` so a CWD-local simulator (`simv`, `verilator`) is discoverable. The note says `run-process` "or a setup node like `resolve-builder`" must replicate it. No current spec captures the behaviour, and skipping it breaks tool discovery in the common rtl_buddy invocation pattern.

#### Concrete steps

1. Decide which module owns the `$PATH` mutation: `run-process` (per-subprocess) or `resolve-builder` (one-shot during setup). Decide once; do not duplicate.
2. Record the chosen owner in `03-module-catalog.md` and in either `specs/03-run-process.md` or `specs/04-setup-modules.md`.
3. Add a test: a subprocess invocation through the chosen module resolves a `.`-relative binary that is not on the inherited `$PATH`.
4. Promote the implementation note from "informational" status to a settled item in `07-ambiguities-and-assumptions.md` once the owner is chosen.

#### Acceptance check

The chosen module's spec explicitly mentions the PATH-prepend behaviour, and a test exercises it.

### 9. Define the `builder_cfg` / `RtlBuilderConfig` schema

**Status: Resolved (2026-06-02).** Builder schema extracted into a dedicated spec
[`specs/01a-builder-schema.md`](implementation-test/specs/01a-builder-schema.md), pinned
to `rtl_buddy/src/rtl_buddy/config/rtl.py:8-126` (`process_opts`,
`RtlBuilderConfigOpts`, `RtlBuilderConfig`). Spec enumerates every field (name, exe,
simv, sim_rand_seed, sim_rand_prefix, opts) with YAML rename targets, the nested
`RtlBuilderConfigOpts` (compile_time/run_time + `process_opts` whitespace-splitting
deserializer), and every method (`get_name`, `get_exe`, `get_simv`, `get_seed`,
`get_modes`, `get_compile_time_opts(mode)`, `get_run_time_opts(mode, seed=None)`)
with returns, behaviour, and the `log.critical`-on-missing-mode/stage idiom for the
two `get_*_opts` methods. The caller-side **Verilator quirk** (callers switch on
`os.path.basename(builder_cfg.get_exe()).startswith("verilator")` to choose
`f"{build_dir}/simv"` over `builder_cfg.get_simv()`, per
`rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:73-80`) is documented in spec 01a and
referenced from every caller spec rather than duplicated. Knock-on edits:
[`specs/01-shared-schema.md`](implementation-test/specs/01-shared-schema.md)
drops the `RtlBuilderConfig` line and adds a `builder.py` reference pointing to 01a;
[`specs/README.md`](implementation-test/specs/README.md) adds row 01a and updates the
parallelism narrative; consumer specs
[`05`](implementation-test/specs/05-selection-expansion-modules.md),
[`07`](implementation-test/specs/07-compile-cycle-modules.md), and
[`08`](implementation-test/specs/08-sim-cycle-modules.md) now name methods
explicitly (`builder_cfg.get_name()`, `get_exe()`, `get_compile_time_opts(mode)`,
`get_run_time_opts(mode, seed)`) with the verilator switch shown at the use site;
[`03-module-catalog.md`](implementation-test/03-module-catalog.md) `filter-reglvl`
entry names `builder_cfg.get_name()` (mirrors
`rtl_buddy/src/rtl_buddy/rtl_buddy.py:350`).

**One discrepancy with the original TODO text.** TODO #9's enumeration listed
`write-filelist` as a `builder_cfg` consumer; neither the catalog (`03-module-catalog.md`
`write-filelist` entry) nor rtl_buddy's source (`vlog_sim.py:88-93`,
`tools/vlog_filelist.py`) bears this out — `write-filelist` takes `ctx` only,
pulling `model_cfg` and the testbench filelist from inside it. Builder config does
not flow through that node. No spec edit needed; the resolution simply does not
extend `builder_cfg` to `write-filelist`.

`resolve-builder`, `filter-reglvl`, `build-compile-cmd`, `resolve-seed`, `build-sim-cmd`, and `write-filelist` all consume a `builder_cfg`/`builder_mode` value (`03-module-catalog.md:47,210,225`; `04-pipeline-and-contracts.md:98`). The shape — fields, types, methods like `get_seed()` — is implicit. `02-payload-conventions.md` does not pin it. (`07-ambiguities-and-assumptions.md` item 1 settles that the YAML config schema is preserved drop-in; the Python types that load it are the implementer's responsibility.)

#### Concrete steps

1. In `specs/01-shared-schema.md`, declare the `RtlBuilderConfig` dataclass (or equivalent) with every field used downstream — at minimum `seed`, `unames`/platform map, the compile/sim/post command shapes, defaults.
2. Declare the methods used by modules (`get_seed()` and others) as members of the class or as free functions over it.
3. Add a `Source:` citation to the rtl_buddy `RtlBuilderConfig` class (paired with the source-traceability todo, TODO #16).
4. Update each downstream module's spec to reference the schema by field, not by guess.

#### Acceptance check

Any module consuming `builder_cfg` can be written without opening rtl_buddy to discover field names.

### 10. Pin the `tests.yaml` and `models.yaml` schemas

**Status: Resolved (2026-06-02).** Same pattern as TODO #9 — schemas extracted into
two dedicated specs:

- [`specs/01b-suite-schema.md`](implementation-test/specs/01b-suite-schema.md), pinned
  to `rtl_buddy/src/rtl_buddy/config/{suite,test,uvm}.py`. Covers `SuiteConfigFile`,
  `SuiteConfig`, `TestbenchConfig`, `TestConfigFile` (raw, with every `field(rename=)`
  including `reglvl`/`plusargs`→`pa`/`plusdefines`→`pd`/`preproc|postproc|sweep` path
  extraction/`testbench`→`tb`/`sim_timeout`→`timeout`), `TestConfig` (runtime, with
  every getter/setter and `get_reglvl`'s four-branch resolution logic), and
  `UVMConfig` (with `__post_init__` validation). Records three Plan B divergences from
  rtl_buddy: lazy model loading ([07 settled 8](implementation-test/07-ambiguities-and-assumptions.md)),
  the `model` → `model_name` rename on the runtime type to avoid the rtl_buddy name
  collision (raw `model: str` becomes runtime `ModelConfig`), and the new
  `suite_dir: Path` field stamped by `parse-suite-config` for downstream `load-model`
  resolution.
- [`specs/01c-model-schema.md`](implementation-test/specs/01c-model-schema.md), pinned
  to `rtl_buddy/src/rtl_buddy/config/model.py`. Covers `ModelConfig`,
  `ModelConfigFile`, `ModelConfigLoader`, plus the `path` field mutation side-effect
  in `get_model`. Records the Plan B divergence at the loader layer: `__init__` and
  `get_model` **raise** instead of `log.critical`ing, so `LoadModelMod` can catch and
  route per-test FAIL (matches [07 settled
  10](implementation-test/07-ambiguities-and-assumptions.md)). Also notes the
  rtl_buddy `get_model_name` bug (returns `self.model_name`, a missing attribute)
  with Plan B's fix (return `self.name`).

Knock-on edits:
[`specs/01-shared-schema.md`](implementation-test/specs/01-shared-schema.md) drops the
`suite.py` / `model.py` / `uvm.py` bullets and adds pointers to 01b / 01c;
[`specs/README.md`](implementation-test/specs/README.md) adds rows 01b and 01c and
updates the parallelism narrative + schema fan-in summary;
[`specs/04-setup-modules.md`](implementation-test/specs/04-setup-modules.md)
`ParseSuiteConfigMod` now names the binding step (`tbs = {tb.get_name(): tb for tb in
raw.testbenches}`), the `suite_dir` stamp, and the `UVMConfig` `ValueError` catch;
[`specs/05-selection-expansion-modules.md`](implementation-test/specs/05-selection-expansion-modules.md)
`SelectTestsMod` / `LoadModelMod` / `ExpandSweepMod` reference fields by name
(`suite_cfg.get_test_names()`, `suite_cfg.get_tests(test_name or None)`,
`ctx["test"].suite_dir`, `ctx["test"].model_path`, `ctx["test"].model_name`,
`ctx["test"].get_sweep_path()`);
[`specs/06-prep-modules.md`](implementation-test/specs/06-prep-modules.md)
`RunPreprocMod` / `WriteFilelistMod` name the field reads (`ctx["test"].get_preproc_path()`,
`ctx["test"].get_testbench().get_filelist()`, `ctx["test"].get_model().get_filelist()`,
`.path`);
[`specs/07-compile-cycle-modules.md`](implementation-test/specs/07-compile-cycle-modules.md)
`BuildCompileCmdMod` names the plusdefines source and the `test_tag` regex (mirrors
`vlog_sim.py:65`);
[`specs/08-sim-cycle-modules.md`](implementation-test/specs/08-sim-cycle-modules.md)
`BuildSimCmdMod` names the plusargs/plusdefines sources and the `get_timeout()` tuple
shape;
[`specs/09-post-modules.md`](implementation-test/specs/09-post-modules.md)
`RoutePostMod` / `ParseUvmLogMod` reference `ctx["test"].uvm` and its fields
explicitly.

`parse-suite-config` reads `tests.yaml` and deserialises "into the schema (spec 01)" (`specs/04-setup-modules.md:24`); `load-model` later reads `models.yaml`. Neither schema is committed to in `specs/01-shared-schema.md` or `02-payload-conventions.md`. (As with TODO #9, `07-ambiguities-and-assumptions.md` item 1 settles that the YAML surface is preserved drop-in but does not name the Python types.)

#### Concrete steps

1. In `specs/01-shared-schema.md`, declare `SuiteConfig`/`TestConfig`/`ModelConfig` dataclasses with every field consumed downstream — at minimum `name`, `model`, `timeout`, `regression_level`, `sweep`, `plusdefines`, `plusargs`, `preproc`, `uvm`.
2. Add `Source:` citations to the rtl_buddy dataclass definitions.
3. State which fields are required vs optional, and the default for each optional.
4. Update each consumer module spec (`select-tests`, `filter-reglvl`, `load-model`, `expand-sweep`, `run-preproc`, `build-compile-cmd`, `build-sim-cmd`, `parse-uvm-log`) to reference the schema by field.

#### Acceptance check

Any consumer module can be written from the spec without reading rtl_buddy source for field names.

### 11. Verify persistent-but-unwired CLI defaults

**Status: Resolved (2026-06-02).** Closed by the same evidence as TODO #6 step 3 (and
07 Settled item 21). Three doc citations confirm a persistent-listed port with a Python
default and no upstream edge passes validation and fires with the default:
`docs/harness/validation.md:39` (default-having ports exempt from edge validation);
`docs/contracts/default.md` invocation precedence step 4 ("Default-valued ports with
nothing queued — omitted from the dict; Python's own default activates"); and
`docs/modules/implementation.md` ("The built-in default contract can use such defaults
without any upstream edge"). No constant-emitter nodes or sentinel-edge workaround is
needed. The plain `test` graph's unwired persistent inputs (`expand-runs.run_ids = [None]`,
`filter-reglvl.reg_level = None`, `filter-reglvl.start_level = None`) fire as written.

### 12. Specify `logs/` directory ownership and lifecycle

**Status: Resolved (2026-06-02).** Ownership lifted out of per-test lazy `makedirs`
into a dedicated [`ensure-logs-dir`](implementation-test/03-module-catalog.md) `unit`
setup node (spec [`04`](implementation-test/specs/04-setup-modules.md)), pinned to
`rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59`. Location stays CWD-relative `logs/`
by default — parity with rtl_buddy's hard-coded literal — but is now overridable via a
new `-L/--logs-dir` CLI flag (recorded as a small Notable divergence in
[`07`](implementation-test/07-ambiguities-and-assumptions.md) Settled 26). Sequencing:
the existing `prepend-path → cc-run/sim-run.env_ready` chain becomes `prepend-path →
ensure-logs → cc-run/sim-run.env_ready`, with an additional `check-cwd → ensure-logs._cwd`
edge so a bad-CWD invocation aborts before any rogue `logs/` is materialised. Lifecycle:
never auto-cleaned (parity); user owns purging. Concurrency: filenames within `logs/`
are uniquely keyed by `<test_name>[_NNNN]` (sweep + run-id), so no within-directory
collisions even under the [`03`](implementation-test/07-ambiguities-and-assumptions.md)
TODO #3 interim serialising shim — no per-test/per-invocation subdir needed.
Knock-on edits: catalog entry + provenance row + persistent-input updates on
`build-compile-cmd` / `build-sim-cmd` / `resolve-seed` + `randseed_path` fold in
[`03-module-catalog.md`](implementation-test/03-module-catalog.md); node row S4.6 and
env-setup narrative in [`04`](implementation-test/04-pipeline-and-contracts.md); CLI
edge + manifest + rewired env_ready edges in
[`06`](implementation-test/06-graph-yaml.md); CLI table row + Notable divergence note +
"Where to invoke" amendment in [`01`](implementation-test/01-cli-and-entry.md);
Settled 26 + updated "CWD assumptions preserved" note + Notable divergence bullet in
[`07`](implementation-test/07-ambiguities-and-assumptions.md); `ctx`-shape extension
for `log` / `randseed_path` and path-composition rule in
[`02-payload-conventions.md`](implementation-test/02-payload-conventions.md); consumer
deliverable + test updates in
[`specs/07-compile-cycle-modules.md`](implementation-test/specs/07-compile-cycle-modules.md)
and [`specs/08-sim-cycle-modules.md`](implementation-test/specs/08-sim-cycle-modules.md).
Regression sibling deferred to [`08`](implementation-test/08-sibling-graphs.md) (its
per-suite `chdir` needs a per-suite bootstrap rather than the once-at-startup `unit`
node used here).

Multiple modules write to `logs/<test>...` (compile log `03-module-catalog.md:150`, sim log/err `:225-226`, randseed `:237`, parse-log input `specs/09-post-modules.md:16`). Who creates `logs/`, when, where (relative to what), and how it interacts with concurrency is not specified. (`07-ambiguities-and-assumptions.md` item 17 defers the broader concurrency story; the "CWD assumptions preserved" implementation note in 07 confirms `logs/` is currently CWD-relative.)

#### Concrete steps

1. Decide the `logs/` location: per-invocation, per-suite, per-test, or CWD-relative.
2. Decide who creates it: a startup node, the first writer, or the harness.
3. Coordinate with TODO #3 (concurrency strategy) — `logs/` placement is the most concrete instance of the parallel-collision risk.
4. Record the decision in `02-payload-conventions.md` (since log paths flow through `ctx`) and `01-cli-and-entry.md` (since a `--logs-dir` CLI option may be needed).

#### Acceptance check

No spec writes to `logs/...` without referencing the documented ownership rule.

### 13. Decide `VlogPost` quirks — replicate or fix

`07` item 15 explicitly defers this: rtl_buddy's `VlogPost` lets a later `PASS` line override an earlier `FAIL` in the same log; partial regex matches behave subtly. `specs/09-post-modules.md:42` and `specs/12-end-to-end.md:34` both depend on the decision.

#### Concrete steps

1. Take a position: replicate the quirks bit-for-bit, or fix them (PASS+FAIL = FAIL; partial match = explicit error).
2. Write the chosen behaviour into `specs/09-post-modules.md` for `ParseLogMod`, naming the fixtures that exercise the chosen edge case.
3. Move the decision out of `07-ambiguities-and-assumptions.md` "Open" into "Settled" (if replicating) or "Notable divergences" (if fixing).
4. Cross-reference from `specs/12-end-to-end.md` so the smoke test asserts the chosen behaviour.

#### Acceptance check

`07` item 15 no longer sits under "Open."

### 14. Confirm sibling-graph scope (resolve `07` item 16)

`07-ambiguities-and-assumptions.md` item 16 sits under "Open — needs your call" asking whether to also design the `randtest` graph (adds `rnd_cnt`/`rnd_rpt`) and the `regression` graph (adds `reg_level`/`start_level` wiring, outer suite loop, per-suite `chdir`). The designs for both already live in `08-sibling-graphs.md`, but item 16 has not been moved out of "Open" — leaving readers unsure whether `08` is a committed scope or a sketch.

#### Concrete steps

1. Confirm whether `08-sibling-graphs.md` is the answer to item 16. If yes, move item 16 from "Open" to "Settled" in `07-ambiguities-and-assumptions.md` with a one-line pointer to `08`.
2. If `08` is a sketch rather than a commitment, record in item 16 what would constitute a commitment (e.g., approved specs in `specs/`) and what blocks it.
3. Update `specs/README.md` and `00-overview.md` if they imply siblings are out of scope — bring those statements in line with the actual scope decision.

#### Acceptance check

`07-ambiguities-and-assumptions.md` item 16 no longer sits under "Open."

### 15. Add a `git-status` equivalent — or explicitly de-scope it

Plan B has no `git-status` module. rtl_buddy records git state alongside test results — useful for reproducibility and bug triage. The plan should make a deliberate decision here, not silently drop it.

#### Concrete steps

1. Decide: include `git-status` in the first port, or de-scope.
2. If including: add a `git-status` module to `03-module-catalog.md` (likely contract `unit`; output: a `git_state` payload or a field on `ctx`). Wire it into the result summary so the recorded `TestResults` carry the git state.
3. If de-scoping: add an entry to `07-ambiguities-and-assumptions.md` under "Notable divergences" naming `git-status` as deliberately dropped, with rationale and a follow-up issue pointer.

#### Acceptance check

A reader can tell at a glance whether git state is recorded with test results, and why.

### 30. Validate the interim parallel-safety shim added by TODO #3

TODO #3 introduced `SerialAcquireContract` and an optional `release_lock` field on
`MergeContract` as an interim shim until upstream `rtl_buddy` per-test artefact directories
land. The mechanism is described in
[`05 — Serialising contracts`](implementation-test/05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture)
and constrained to the plain `test` graph (R=1), but its concurrency properties are
asserted, not proven. TODO #4 explicitly scoped that work to the original `MergeContract`
semantics; this TODO covers the shim.

Because the shim is **explicitly temporary** (removed when `07` item 17's upstream change
lands), this TODO's outputs live in the implementation-test plan and tests only — do not
promote either piece to `docs/contracts/index.md` as first-class. Treat the validation work
itself as removable alongside the shim.

#### Concrete steps

1. **Formal description of the acquire side.** Extend
   [`05 — Serialising contracts`](implementation-test/05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture)
   with a `SerialAcquireContract` invariants block parallel to the merge one: state held
   (the shared `_LOCKS` dict, the inherited `DefaultContract` port state), lock acquisition
   timing relative to upstream `await`, `EndSentinel` short-circuit (no acquire), and
   interaction with `DefaultContract`'s persistent-input precedence (the lock must not be
   acquired for invocations that resolve entirely from persistent caches with no consumed
   work item — verify this matches the design intent).
2. **Formal description of the release side.** In the same section, document the
   `release_lock` branch of `MergeContract` distinctly from the base contract: one release
   per delivered payload, none on `EndSentinel`, fail-fast on missing prior acquire, and
   the pairing invariant ("every acquired item must reach `agg`") repeated from the
   Constraints block.
3. **Pairing-arithmetic test.** Add a new test file (`contracts/tests/test_serial.py`) or
   extend `test_merge.py`. Enumerate cases for the spec at
   [`specs/02-merge-contract.md`](implementation-test/specs/02-merge-contract.md) (or a
   new sibling spec):
   - acquire then release through the merge → second acquire blocks until release fires;
   - acquire then `EndSentinel` (no item reaches merge) → release never fires, lock is
     left held (documented as invariant violation; verifies fail-fast surfaces);
   - `release_lock` configured but no `serial_acquire` upstream → first delivered payload
     raises `RuntimeError` from `asyncio.Lock.release()`;
   - shared-state check: instantiate two contracts with the same `lock_name`; confirm
     they share the same `asyncio.Lock` object via the module-level `_LOCKS` registry.
4. **End-to-end check.** Inside [`specs/12-end-to-end.md`](implementation-test/specs/12-end-to-end.md),
   add a smoke case that exercises the shim under concurrency: two tests with overlapping
   compile/sim regions; assert that the second test's `cc-run` does not start until the
   first test's terminal result has been delivered to `agg`. This is the actual property
   the shim exists to provide.
5. **Removal plan.** Add a one-line "Removal" subsection at the foot of
   [`05 — Serialising contracts`](implementation-test/05-branching-and-results.md#serialising-contracts--interim-parallel-safety-posture)
   stating the trigger (upstream `rtl_buddy` per-invocation subdirs lands and `07` item 17
   moves out of Deferred), the artefacts to delete (`SerialAcquireContract`, the
   `release_lock` Config field on `MergeContract`, the `_LOCKS` registry, the wiring in
   `04` rows 7 & 22 and `06`), and the tests added by this TODO that must also be deleted.

#### Acceptance check

The interim shim's correctness is supported by enumerated tests and a written invariant
that explicitly notes the temporary status and removal plan. No `docs/contracts/index.md`
entry exists for `serial_acquire` (deliberately — to prevent it from becoming load-bearing).

## Spec polish — required to make specs buildable

### 16. Strengthen source traceability to rtl_buddy

Today, rtl_buddy provenance for each module lives only in the single table at the bottom of `03-module-catalog.md` (rows like `| derive-seed-mode | rnd_new/rnd_last → SeedMode in do_cmd_test |`). Those rows name methods but omit file paths, line ranges, and the rtl_buddy version they are anchored to, and they do not propagate into the per-module catalog entries or into the `specs/` implementation tickets where the work is actually done.

Goal: an implementer building any module should, without leaving that module's section, know exactly which rtl_buddy file and line range they must mirror, and which rtl_buddy version the citation is anchored to.

#### Concrete steps

1. **Pin the rtl_buddy version.** Add a `Source baseline:` line near the top of `00-overview.md` naming the exact rtl_buddy tag or commit SHA the plan mirrors. If the rtl_buddy source is not already expected as a sibling checkout, declare its expected path (e.g., `../rtl_buddy/`). All file:line citations are valid only against this version.

2. **Inline per-module citations in `03-module-catalog.md`.** For each module entry (e.g., `derive-seed-mode`, `resolve-seed`, `write-randseed`, `interpret-sim`, `early-stop-gate`, …), add a `Source:` line immediately after the one-line description, in this shape:

   ```
   Source: rtl_buddy/src/rtl_buddy/<file>.py:L<start>-L<end> — <one-line note on what's there>
   ```

   When a module mirrors fragments from more than one rtl_buddy site, list each on its own line. The line ranges should bound the *behaviour* being mirrored, not the enclosing class — typically the body of one method or a contiguous block within one. Verify each range by opening the file and reading it; do not derive ranges from method names alone.

3. **Replace the bottom provenance table with a derived view.** Once every module has an inline `Source:` line, the table at the foot of `03-module-catalog.md` becomes a duplicate. Drop it, or rebuild it as a one-column index that links to the inline citations. Avoid keeping two sources of truth that can drift.

4. **Propagate citations into `specs/` tickets.** Each implementation ticket already lists the modules it builds. For every such module, add a `Compatibility source:` bullet beneath that module's task in the ticket, copying the citation from `03-module-catalog.md`. An implementer reading a `specs/` file should not need to flip back to the catalog to find what they are mirroring.

5. **Cover non-module sites.** The same treatment applies to:
   - **CLI mapping** (`01-cli-and-entry.md`): the existing flag table references rtl_buddy flag names; extend each row with the file:line range of that flag's definition (typically in `rtl_buddy/src/rtl_buddy/rtl_buddy.py`).
   - **Contract behaviour** (`05-branching-and-results.md`): where the new `MergeContract` reproduces a piece of `do_cmd_test`'s coordination, cite the relevant rtl_buddy lines.
   - **Payload conventions** (`02-payload-conventions.md`): where `ctx`/`result` shapes mirror rtl_buddy types (e.g., `TestConfig`, `TestResults`, `SeedMode`), cite the dataclass/enum definition site.

6. **Anchor against drift.** Add a one-line note at the top of `03-module-catalog.md` and `specs/README.md`: "All `Source:` and `Compatibility source:` citations are anchored to rtl_buddy *\<pinned version\>*. If rtl_buddy is updated, re-verify every cited range." This makes the traceability self-auditing.

7. **Cross-link to "Notable divergences".** `07-ambiguities-and-assumptions.md` already lists deliberate departures from rtl_buddy under "Notable divergences." For each divergence entry, add the rtl_buddy file:line citation it departs from, and from each module's `Source:` line, link forward to the divergence entry when one applies. This lets a reader see the rtl_buddy behaviour and the design's intentional departure side by side.

#### Acceptance check

A reader who picks up any `specs/` ticket should be able to:

- Open the cited file at the cited line range in rtl_buddy.
- Confirm that the rtl_buddy code at those lines matches the module's catalog description of what it mirrors.
- Identify whether the module mirrors the source faithfully or departs deliberately (via the cross-link to "Notable divergences").

The work is mechanical but each citation must be verified by reading the cited code — not inferred from method names — or the traceability becomes a liability.

### 17. Split grouped module specs into per-module tickets

`specs/` tickets currently group 4–6 modules per file (e.g., `specs/08-sim-cycle-modules.md` covers `ExpandRuns`, `ResolveSeed`, `BuildSimCmd`, `WriteRandseed`, `LinkLatest`, `InterpretSim`). This makes work units large, parallelisation graphs coarse, and crowds each module's signature, tests, and constraints into shared space.

#### Concrete steps

1. For each grouped spec, split into one file per module (e.g., `08a-expand-runs.md`, `08b-resolve-seed.md`, …). Keep the parent file as a thin index linking to the children, or remove it.
2. Each child spec uses the same boilerplate: `Depends on:`, `References:`, `Goal`, `Deliverables`, `Tests`, `Acceptance criteria`, `Notes`.
3. Update `specs/README.md`'s priority table to list the new per-module specs and which can run in parallel.

### 18. Include module code skeletons inside the spec

Module skeletons (`class Foo: def run(self, ...): ...`) currently live only in `03-module-catalog.md`. Build tickets reference them by link, forcing the implementer to flip between two files while writing code.

#### Concrete steps

1. For each module spec, copy the `run()` signature and a minimal body sketch from the catalog into the spec.
2. Treat the catalog version as the design view; the spec version is the build view. Update both when behaviour changes.

### 19. Inline the I/O surface block in every module spec

Each module's contract / inputs / outputs surface should appear in its own spec, not only in the catalog. Use a fenced block:

```
contract: <name>[, <key>: <value>]
inputs:  <port>: <type>[, ...]
outputs: <port> → <type>
         <port> → <type>
```

#### Concrete steps

1. Place the block immediately before the implementation steps in each module spec.
2. Flag persistent inputs explicitly (e.g., `persistent_inputs: [seed_mode, builder_cfg]`).
3. Include a `contract_config:` line whenever the contract takes non-default configuration.

### 20. Add a "Before you start" reading list to every spec

Specs should open with an explicit reading list: harness docs the implementer must read, rtl_buddy source they will mirror, and sibling specs they share state with. Today the implementer is expected to discover this themselves.

#### Concrete steps

1. Add a `## Before you start` section at the top of each spec (after `Depends on:` / `References:`).
2. Include: relevant rtl_comrade docs (`docs/modules/implementation.md` for any module spec; `docs/contracts/implementation.md` for any contract spec); the rtl_buddy file path + line range the module mirrors (paired with TODO #16, source traceability); any sibling specs that append to the same file.
3. Every link must resolve inside this repo.

### 21. Inline file path and manifest entries in each spec

Specs currently say "Manifest entries per [06]" — the implementer must open `06-graph-yaml.md` to find the manifest line for each module. Move the exact additions into the spec.

#### Concrete steps

1. For each module spec, state the target file path explicitly (e.g., `File: modules/rtl_test/sim.py`).
2. Include the exact YAML to append to `modules/config.yaml` (and the contracts manifest where relevant).
3. If the file is shared across specs, name which earlier spec creates it and which later specs append to it (see TODO #26, forward-reference notes).

#### Acceptance check

A reader can build and register the module without opening any file other than the spec.

### 22. Expand each module's algorithm into numbered implementation steps

Implementation prose is currently one-liner bullets. Anything with branching, file I/O, exception handling, or multi-step state changes should be a numbered step list.

#### Concrete steps

1. For each non-trivial module, expand the implementation prose into numbered steps.
2. Each step is one paragraph: what to do, what to read/write, what to emit.
3. Failure paths get their own steps — not parenthetical asides.

### 23. Add a "Constraints" section to every spec

Specs need a foot section enumerating what the implementer must NOT do, plus invariants the code must hold. Currently constraints are inferred from prose or from the parent design files.

#### Concrete steps

1. Add a `## Constraints` section at the foot of each module spec.
2. Include: numeric ranges (`random.randrange(1_000_000)`, not `1_000_001`); the failure idiom the module follows (port-routed vs `log.error` vs `log.critical` — see TODO #2, failure integration); harness invariants the module honours (single-source-per-port, EndSentinel propagation, no graph awareness).
3. Phrase as imperatives: "Use…", "Do not…", "Failure on X must…".

### 24. Enumerate test cases with input/expected pairs

Tests sections currently list 1–2 bullets per module covering the happy path. Each module should enumerate cases explicitly.

#### Concrete steps

1. Expand each module's Tests section to list cases in `<input> → <expected output>` form, one per bullet.
2. Cover: every named output port hit at least once; every failure mode; every boundary value (zero, max, missing, malformed).
3. Name any harness fixture used (test-double for a contract, mock subprocess for `run-process`, etc.).

#### Acceptance check

Every module has at least four enumerated test cases, or all reachable output ports plus boundary inputs, whichever is larger.

### 25. Spell out filename and format placeholders

Specs use placeholders like `[_NNNN]` and `<test>` that hide exact format details (padding width, file extensions, hidden-file conventions). Where the format matters, spell it out with an example expansion.

#### Concrete steps

1. Audit each spec for placeholders in filename conventions, padding patterns, and format strings.
2. Replace with explicit format specifiers (e.g., `:04d` zero-padding) paired with an example (`test_0003.randseed`).
3. Where the format is set by rtl_buddy, cite the rtl_buddy line that defines it (paired with TODO #16, source traceability).

### 26. Add forward-reference notes between specs that share a file

When multiple specs add to the same Python file, the spec creating the file should announce which later specs append to it; appending specs should announce what they assume the file already contains. Today dependency direction goes one way (`Depends on:`); the forward direction is uncaptured.

#### Concrete steps

1. For each spec that creates a new file, add a "This file receives further additions from specs X, Y, Z" line.
2. For each spec that appends to an existing file, add a "This file is created by spec N. Append (do not overwrite)." line.
3. Update `specs/README.md` to summarise which files are shared across specs.

### 27. Expand "Acceptance criteria" to enumerate observable behaviour

Current Acceptance sections are coarse ("Tests pass. End-to-end produces correct files"). They should enumerate observable behaviours: which output ports, which failure paths, which artefacts produced.

#### Concrete steps

1. Replace coarse acceptance prose with a bullet list: every named output port exercised; every failure idiom exercised; the registry entry resolvable by the harness; the manifest validates.
2. Where end-to-end is required, name the rtl_buddy fixture/suite the test runs against and the exact files/symlinks it produces.

#### Acceptance check

Every spec's Acceptance section is a bullet list referencing concrete artefacts (port names, files, fixtures), not just "tests pass."

## Cosmetic

### 28. Pin the module file-layout and package conventions

`06-graph-yaml.md` suggests grouping modules into `setup.py`, `build.py`, `sim.py`, `control.py` (also implicit in `specs/04-setup-modules.md:13` → `modules/rtl_test/setup.py`). This is described as a "suggestion" rather than a pinned layout, leaving the package shape ambiguous.

#### Concrete steps

1. Commit to a package name (`modules/rtl_test/`) and the final file grouping (which module goes into which file).
2. Record the mapping in `06-graph-yaml.md` (or a new section in `specs/README.md`).
3. Pin the plugin manifest namespace (e.g., `rtl_test:derive-seed-mode`) so modules cannot collide with sibling graphs.

#### Acceptance check

Every module spec names exactly one file path, and that file path matches the committed layout.

### 29. Clarify the dataflow diagram

The ASCII diagram in `00-overview.md` mixes main-line and config edges; the layout is visually congested and a few branches collapse into the same column. The node table in `04-pipeline-and-contracts.md` compensates, but a clearer diagram would help reviewers trace the graph at a glance.

#### Concrete steps

1. Split the existing diagram into two: main-line dataflow only; config / persistent-input edges only.
2. Consider producing a graphical version (mermaid, or generated from `06-graph-yaml.md`).
3. Cross-reference both diagrams from the node table in `04-pipeline-and-contracts.md`.

#### Acceptance check

A reviewer can trace any single edge type without visual conflict from another.

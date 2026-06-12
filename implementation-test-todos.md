# implementation-test todos

Todos for bringing the `implementation-test/` plan to a buildable, internally consistent state. Items are grouped into three sections by priority:

- **Design-level** — open questions, unresolved decisions, and structural gaps that must be settled *before* per-spec polish is meaningful. Most of these correspond to items in `implementation-test/07-ambiguities-and-assumptions.md` under "Open", "Deferred (KIV)", and "To verify against the framework before building"; cross-references appear inline as `07` item *N*.
- **Spec polish** — patterns that need to be applied to each `specs/` ticket so that an implementer can build a module from the spec alone, without flipping between catalog, design files, and rtl_buddy source.
- **Cosmetic** — small structural improvements; not blocking.

Items are numbered globally for cross-referencing (e.g., "see TODO #5"). The order within each section reflects rough priority but is not load-bearing — items in the same section can be picked up in parallel where dependencies allow.

> **Note on the index.** `implementation-test-todos-index.md` mirrors the status of every item here. After resolving a todo (or otherwise changing its status), update its row in the index too so the two stay in sync.

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

**Revised by TODO #15 (2026-06-10).** The centralised `aggregate-results.finalise()` ERROR is
gone with the node; the per-emission `log.error` at each failure site is now the **sole**
deferred-exit driver (no longer belt-and-braces). The per-site decisions are otherwise
unchanged. See [05 — Result aggregation and exit code](implementation-test/05-branching-and-results.md#result-aggregation-and-exit-code).

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

> **Superseded by TODO #30 (2026-06-10).** The serialising-contract posture below was
> **removed**. TODO #15 deleted its release node (`fan-in`), and rather than rebuild the lock,
> TODO #30 adopted **option (c)-style per-tag artefact naming** instead: `write-filelist` writes
> `run.{test_tag}.f` and the other artefacts were already per-tag, so the region runs concurrent
> with no lock. `07` item 17 (upstream per-invocation subdirs) is kept as the reference fix for
> the residual. The original option-(b) write-up is retained below for the record. See TODO #30.

**Status: Resolved (2026-05-31; posture replaced 2026-06-10 — see banner).** Posture chosen:
option (b), a serialising contract on the compile/sim region. The hazard is that a concurrent next-test compile would stomp the prior
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
[`05 — Interim CWD-collision posture`](implementation-test/05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming)
(the section that replaced the removed shim write-up);
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

### 4. Specify and validate the `any` contract and `fan-in-results` module

**Status: Resolved (2026-06-05).** The `MergeContract` design this item previously
validated is replaced by a `fan-in-results` module (`run(self, **inputs)`, edge-derived
ports via the non-definite-inputs mechanism) paired with a general-purpose `any` contract.
The redesign eliminates the harness-change prerequisite that was blocking spec 02. All
design-level work is complete:

1. **Formal description of `any` contract** (the sketch + invariants now live in
   [`specs/02`](implementation-test/specs/02-any-contract-and-fan-in.md); a pointer remains at
   [`05 — The any contract`](implementation-test/05-branching-and-results.md#the-any-contract-retained-currently-unwired)):
   `_pending` task dict state, per-port `EndSentinel` handling, no-loss invariant
   (multi-done-per-wake), drainage order, termination rule, and `release_lock` side-effect.
2. **Module and test spec** written in
   [`specs/02-any-contract-and-fan-in.md`](implementation-test/specs/02-any-contract-and-fan-in.md):
   `AnyContract` sketch, `FanInResultsMod` sketch, behavioural tests, ≥13-port stress
   test, property-based test, `FanInResultsMod` unit tests, and acceptance criteria.
3. **Docs promotion** deferred to implementation time — captured as an acceptance
   criterion in spec 02 (add `docs/contracts/index.md` entry listing invariants, both
   contract and module, and reusability note; `release_lock` flagged as interim per
   TODO #30).

The `SerialAcquireContract` + `any.release_lock` interim shim is **not** in scope for
TODO #4 — tracked separately in TODO #30.

**Superseded by TODO #15 (2026-06-10).** The `fan-in-results` module and `aggregate-results`
sink validated here are **removed**: terminal re-convergence is no longer a graph node, the
summary is a `SummaryProcessor` logging plugin, and the terminal ports are unwired. The `any`
contract (and its spec/tests in [`specs/02`](implementation-test/specs/02-any-contract-and-fan-in.md))
is retained as reusable infrastructure but is **no longer wired** in the `test` graph. See
TODO #15 and [07 item 27](implementation-test/07-ambiguities-and-assumptions.md).

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
  one VAR_KEYWORD port, not arbitrary inference. The non-definite-inputs mechanism
  (`graph.py:95-97`) resolves this: when a module's `run()` uses `**kwargs`, ports are
  populated from the graph edges at load time. Design uses a `fan-in-results` module
  (`run(self, **inputs)`, edge-derived ports) with a general-purpose `any` contract;
  `aggregate-results` retains `run(self, result)` with `default`. No harness change
  required. See updated item 19 in `07-ambiguities-and-assumptions.md`.
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

**Status: Resolved (2026-06-05).** `08-sibling-graphs.md` is a modularity analysis
demonstrating the extension cost of the sibling graphs (1 new module for `randtest`;
2 new modules + 1 contract switch for `regression`), not a build commitment. Sibling
graphs are not deliverables of this plan. `07` item 16 moved to Settled; `specs/README.md`
updated to reflect the analysis framing; `00-overview.md` needed no change (describes
the `test` graph only throughout).

`07-ambiguities-and-assumptions.md` item 16 sits under "Open — needs your call" asking whether to also design the `randtest` graph (adds `rnd_cnt`/`rnd_rpt`) and the `regression` graph (adds `reg_level`/`start_level` wiring, outer suite loop, per-suite `chdir`). The designs for both already live in `08-sibling-graphs.md`, but item 16 has not been moved out of "Open" — leaving readers unsure whether `08` is a committed scope or a sketch.

#### Concrete steps

1. Confirm whether `08-sibling-graphs.md` is the answer to item 16. If yes, move item 16 from "Open" to "Settled" in `07-ambiguities-and-assumptions.md` with a one-line pointer to `08`.
2. If `08` is a sketch rather than a commitment, record in item 16 what would constitute a commitment (e.g., approved specs in `specs/`) and what blocks it.
3. Update `specs/README.md` and `00-overview.md` if they imply siblings are out of scope — bring those statements in line with the actual scope decision.

#### Acceptance check

`07-ambiguities-and-assumptions.md` item 16 no longer sits under "Open."

### 15. Add a `git-status` equivalent — or explicitly de-scope it

**Status: Resolved (2026-06-10).** Decision: **include** git state — recorded as a *logging*
concern, not a graph-routed payload. The resolution went further than the minimal question,
adopting the full redesign worked out in `findings.md`: the results summary leaves the graph
entirely. Concretely:

- A new [`git-status`](implementation-test/03-module-catalog.md) `unit` setup node calls
  `log.info("git_state", branch=..., sha=..., dirty=...)` once. No graph routing, no
  persistent inputs, no payload surgery — which is the whole reason this is now a one-line
  node rather than the awkward fan-in wiring the original ticket anticipated.
- `fan-in-results` and `aggregate-results` are **removed**. The 13 terminal ports are left
  **unwired** (`no_destination` at INFO); each terminal node calls
  `log.info("test_result", ...)` at emission. A per-graph **`SummaryProcessor`** (a single
  stateful structlog processor in `graphs/log/summary.py` — **not** a `logging.Handler`)
  accumulates the `test_result` events (**results only**) and renders the table in its
  `finalise()` teardown hook; it also `DropEvent`s each row so no separate `drop_summary_events`
  processor is needed. `git_state` is not collected — it falls through to the console.
  (*Plugin form revised 2026-06-11; the original handler form is described in TODO #31. The
  redesign assumes the processor-finalisation hook — see
  [07 item 27](implementation-test/07-ambiguities-and-assumptions.md).*)
- The exit code is driven **solely** by the per-emission `log.error` at each failure site
  (the old `aggregate-results.finalise()` belt-and-braces ERROR is gone).

Design, sketches, and the CRITICAL-path reasoning are in
[`05 — Re-convergence`](implementation-test/05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node);
spec in [`specs/10`](implementation-test/specs/10-control-aggregate-modules.md); graph + logging
block + manifest in [`06`](implementation-test/06-graph-yaml.md); node rows in
[`04`](implementation-test/04-pipeline-and-contracts.md); catalog entry +
`fan-in`/`aggregate` removal in [`03`](implementation-test/03-module-catalog.md);
[`07`](implementation-test/07-ambiguities-and-assumptions.md) Settled item 27 (supersedes
items 3, 19; revises 9, 10). Overview, payload conventions, and sibling-graph analysis
([`00`](implementation-test/00-overview.md), [`02`](implementation-test/02-payload-conventions.md),
[`08`](implementation-test/08-sibling-graphs.md)) updated to match.

**Knock-on — TODO #30 resolved by removing the shim.** Deleting `fan-in` removed the interim
parallel-safety shim's lock-*release* site (it lived on the `any` contract's `release_lock`
field on `fan-in`), leaving the `serial_acquire` *acquire* on `write-filelist` with nothing to
release it. Rather than relocate the release, **TODO #30 removed the shim entirely** in favour
of **per-tag artefact naming** (`write-filelist` writes `run.{test_tag}.f`; `obj_dir`/
verilator-`simv`/logs were already per-tag) — same correctness, no lock, and the region stays
concurrent. The residual shared-CWD artefacts (non-verilator `simv`, `test.*` symlinks,
tool-internal files) remain the job of the **upstream per-invocation-subdir change**, which is
kept on the books as the reference fix (`07` item 17). See TODO #30 and
[`05 — Interim CWD-collision posture`](implementation-test/05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming).
The `any` contract itself is retained as a plain reusable contract but is now unwired in
`test` ([spec 02](implementation-test/specs/02-any-contract-and-fan-in.md)).

The original investigation and three-way decision below are kept for the record.

Plan B has no `git-status` module. rtl_buddy records git state alongside test results — useful for reproducibility and bug triage. The plan should make a deliberate decision here, not silently drop it.

#### Concrete steps

1. Decide: include `git-status` in the first port, or de-scope.
2. If including: add a `git-status` module to `03-module-catalog.md` (likely contract `unit`; output: a `git_state` payload or a field on `ctx`). Wire it into the result summary so the recorded `TestResults` carry the git state.
3. If de-scoping: add an entry to `07-ambiguities-and-assumptions.md` under "Notable divergences" naming `git-status` as deliberately dropped, with rationale and a follow-up issue pointer.

#### Acceptance check

A reader can tell at a glance whether git state is recorded with test results, and why.

### 30. Validate the interim parallel-safety shim added by TODO #3

**Status: Resolved (2026-06-10) — shim removed, not validated.** TODO #15 deleted the `fan-in`
node that carried the shim's lock *release* (`AnyContract.release_lock`), leaving the
`serial_acquire` *acquire* on `write-filelist` with nothing to release it. Rather than relocate
the release and then validate a lock that bought correctness-not-parallelism (it held the lock
across the whole compile/sim region), the shim was **removed entirely** and replaced with
**per-tag artefact naming** (decision (B)):

- **`write-filelist` writes `run.{test_tag}.f`** (the one shared filename the graph fully
  controls) and emits that `Path`; `build-compile-cmd` already passes `filelist["filelist"]`
  to `-f`, so no edge or downstream change. `obj_dir_<tag>/`, the verilator `simv`, and the
  `logs/` paths were already per-tag. Concurrent tests therefore no longer collide on
  graph-named artefacts, **with no lock and no loss of concurrency**.
- **Deleted:** `SerialAcquireContract`, `contracts/serial.py`, the `_LOCKS` registry, the
  `release_lock` Config field on `AnyContract` (now a plain contract), the `serial_acquire`
  wiring on `write-filelist` (reverts to `default`), and the contracts-manifest entry. The
  planned `test_serial.py` / end-to-end shim-concurrency test are **not** written.
- **Kept:** `07` item 17 (the upstream per-invocation-subdir change) as the **reference fix**.
  Per-tag naming is an explicit graph-local *shadow* of it and is itself removed when item 17
  lands. The residual it cannot name — non-verilator `simv` (fixed `builder_cfg.get_simv()`),
  the `test.*` "latest" symlinks (last-writer-wins), tool-internal CWD writes — stays with
  item 17; **do not re-introduce a lock** for it.

Edits: shim section in [`05`](implementation-test/05-branching-and-results.md#interim-cwd-collision-posture--per-tag-artefact-naming)
rewritten as "Interim CWD-collision posture — per-tag artefact naming"; `04` node row 7 +
contract list + subsection; `06` `filelist` node + contracts manifest (no `serial.py`); `03`
`write-filelist` entry + caveat; `07` item 17 interim posture + Notable divergences + item 27
knock-on; `specs/02` (`AnyContract` de-`release_lock`'d), `specs/06`/`07`/`08` (per-tag run.f +
residual notes), `specs/11` (manifest note). See TODO #3 (the shim it introduced) and TODO #15.

#### Acceptance check

The compile/sim region runs concurrently without artefact collisions on any graph-named file,
with **no** serialising contract. No `serial_acquire`/`serial.py`/`_LOCKS` remain in the plan.
The residual non-renameable artefacts are documented against `07` item 17, which stays
Deferred as the reference fix.

## Spec polish — required to make specs buildable

### 16. Strengthen source traceability to rtl_buddy

**Status: Resolved (2026-06-10).** All seven steps done, anchored to rtl_buddy **`v1.4.0`**
(commit `a69d962`, the sibling checkout at `rtl_buddy/`):

1. **Version pinned** — `Source baseline` blockquote added near the top of
   [`00-overview.md`](implementation-test/00-overview.md) naming the tag, SHA, and expected
   path.
2. **Inline per-module citations** — every module entry in
   [`03-module-catalog.md`](implementation-test/03-module-catalog.md) now carries a
   `- **Source:**` line with verified file:line ranges (each opened and read, not inferred
   from method names); multi-site modules (`run-process`, `interpret-compile`/`-sim`,
   `build-compile-cmd`, etc.) list each site. `check-suite-cwd` records "no direct analogue".
3. **Provenance table replaced** — the flat bottom table (a second copy of the line ranges)
   was dropped in favour of a pointer to the inline `Source:` lines as the single source of
   truth, avoiding drift.
4. **Propagated into specs** — every module ticket in `specs/04`–`specs/10` (plus
   `specs/03`) gained a `Compatibility source:` bullet copying the catalog citation;
   `specs/README.md` carries the anchoring note.
5. **Non-module sites covered** — CLI flag table in
   [`01-cli-and-entry.md`](implementation-test/01-cli-and-entry.md) gained an `rtl_buddy src`
   column (each flag's `do_cmd_test`/`root_options` definition line); payload types in
   [`02-payload-conventions.md`](implementation-test/02-payload-conventions.md) (`TestConfig`,
   `ModelConfig`, `SeedMode`, the `TestResults` family) cite their definition sites; the exit
   code + summary coordination in
   [`05-branching-and-results.md`](implementation-test/05-branching-and-results.md) cites the
   `do_cmd_test` summary loop + `exit_code |=` line (the old `MergeContract` this step named
   was removed by TODOs #4/#15, so the citation targets the surviving logging/exit design).
6. **Drift anchors** — one-line "re-verify on rtl_buddy update" notes at the top of
   `03-module-catalog.md` and `specs/README.md`.
7. **Cross-linked divergences** — each entry under "Notable divergences" in
   [`07-ambiguities-and-assumptions.md`](implementation-test/07-ambiguities-and-assumptions.md)
   now cites the rtl_buddy file:line it departs from; the catalog `Source:` lines link forward
   to the matching Settled/divergence entry where one applies.

The original ticket text is kept below for the record.

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

**Status: Resolved (2026-06-10).** Each grouped spec (`specs/04`–`specs/10`) is split into
one ticket per module/deliverable, with the numbered file kept as a thin index linking to
its children (preserving every existing cross-reference into `specs/0N-...md`). 31 child
tickets were created: 04a–04i (9), 05a–05f (6), 06a–06b (2), 07a–07b (2), 08a–08f (6),
09a–09c (3), 10a–10c (3). Each child carries the standard boilerplate (`Depends on:` /
`References:` / `Goal` / `Deliverables` / `Tests` / `Acceptance criteria` / `Notes`), the
module's verbatim failure-handling + `Compatibility source:` blocks, its own test bullets,
and a per-module acceptance list; cross-module integration acceptance stays on the parent
index. Shared content was distributed to the right child (e.g. the `exec_hook` helper note
to 05f/06a, the per-tag-filelist concurrency posture to 06b/07a, the `keyed_join` note to
07b/08d). `specs/README.md`'s priority table now flags each numbered spec as an index and
adds a per-module child table with the intra-group dependency notes. Concrete-step (1)
chose "keep the parent file as a thin index" over removal.

The original ticket text is kept below for the record.

`specs/` tickets currently group 4–6 modules per file (e.g., `specs/08-sim-cycle-modules.md` covers `ExpandRuns`, `ResolveSeed`, `BuildSimCmd`, `WriteRandseed`, `LinkLatest`, `InterpretSim`). This makes work units large, parallelisation graphs coarse, and crowds each module's signature, tests, and constraints into shared space.

#### Concrete steps

1. For each grouped spec, split into one file per module (e.g., `08a-expand-runs.md`, `08b-resolve-seed.md`, …). Keep the parent file as a thin index linking to the children, or remove it.
2. Each child spec uses the same boilerplate: `Depends on:`, `References:`, `Goal`, `Deliverables`, `Tests`, `Acceptance criteria`, `Notes`.
3. Update `specs/README.md`'s priority table to list the new per-module specs and which can run in parallel.

### 18. Include module code skeletons inside the spec

**Status: Resolved (2026-06-10).** Every module spec — `specs/03` (run-process) plus the 30
per-module child tickets `04a`–`10b` — now carries a `## Surface` section inserted between
`## Goal` and `## Deliverables`, containing the module's `class …Mod` skeleton: the `run()`
signature and a minimal body sketch mirroring the catalog
([`03-module-catalog.md`](implementation-test/03-module-catalog.md)) entry, with `Config`
shown for the two config-bearing modules (`discover-config-file`, `early-stop-gate`) and
generators used where a module emits on multiple ports (the harness has no multi-port single
return — `node.py:218`). The skeleton is labelled the *build view*; the catalog stays the
*design view*, and the two are to be updated together (step 2). **Out of scope:** `specs/10c`
(the `SummaryProcessor` logging plugin is a structlog processor, not a graph module with `run()`
— tracked separately in TODO #31) and `specs/02` (a contract — its reading list is TODO #20's
concern). Resolved jointly with TODO #19, which shares the same `## Surface` section. The
original ticket text is kept below.

Module skeletons (`class Foo: def run(self, ...): ...`) currently live only in `03-module-catalog.md`. Build tickets reference them by link, forcing the implementer to flip between two files while writing code.

#### Concrete steps

1. For each module spec, copy the `run()` signature and a minimal body sketch from the catalog into the spec.
2. Treat the catalog version as the design view; the spec version is the build view. Update both when behaviour changes.

### 19. Inline the I/O surface block in every module spec

**Status: Resolved (2026-06-10).** The same `## Surface` section added for TODO #18 opens
with a fenced I/O block in the prescribed shape (`contract:` / `inputs:` / `outputs:`),
extended with: a `config:` line for module `Config` fields (step 2-adjacent); a
`contract_config:` line wherever the contract itself takes configuration (`keyed_join`'s
`key_field: key` on `interpret-compile` / `write-randseed`) (step 3); and a
`persistent_inputs:` line flagging the persistent ports on every `default`-contract module
(step 2). The block sits immediately before the implementation (`## Deliverables`) in each of
the 31 module specs (step 1). `specs/10c` / `specs/02` excluded for the same reasons as
TODO #18 (10c tracked separately in TODO #31). The original ticket text is kept below.

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

**Status: Resolved (2026-06-11).** Module / contract / logging-plugin categories done here;
the remaining categories (schema, graph/manifest, end-to-end) and the index/README exemption
were completed under TODO #32, and step 2 now names a reading list for every category. A
`## Before you start` section now opens every spec in the module/contract/logging categories
(inserted after `Depends on:` / `References:`, before `## Goal`):

- **Module specs** (31): `specs/03` plus `04a`–`04i`, `05a`–`05f`, `06a`–`06b`, `07a`–`07b`,
  `08a`–`08f`, `09a`–`09c`, `10a`, `10b`. Each names `docs/modules/implementation.md` (port
  inference, output forms, `finalise()`, config-bearing modules) with `modules/io.py` /
  `modules/funcs.py` as the shipped examples, points at the spec's own **Compatibility source**
  entry for the rtl_buddy file:line it mirrors (anchored to `v1.4.0`, commit `a69d962`; paired
  with TODO #16), and names the sibling specs appending to the same `modules/rtl_test/*.py`
  file (grouped by file: `setup.py`, `build.py`, `sim.py`; `10a` is the sole occupant of
  `control.py`).
- **Contract spec** (`specs/02`): names `docs/contracts/implementation.md` (`get_inputs()`,
  the `ContractPort` API, termination/`EndSentinel`, contract-owned state) and `docs/contracts/index.md`;
  records that `any` is a standalone `contracts/any.py` plugin with no file-sharing siblings.
- **Logging-plugin spec** (`specs/10c`): already carried its section (TODO #31).

All cited links resolve inside the repo. The remaining spec categories step 2 never named —
schema (`01`/`01a`/`01b`/`01c`), graph/manifests (`11`), end-to-end (`12`), the thin parent
indexes (`04`–`10`), and `specs/README.md` — were handled under **TODO #32** (resolved).

The original ticket text is kept below for the record.

#### Concrete steps

1. Add a `## Before you start` section at the top of each spec (after `Depends on:` / `References:`).
2. Include the relevant rtl_comrade docs per spec category, the rtl_buddy file path + line range the spec mirrors (paired with TODO #16, source traceability), and any sibling specs that append to the same file. Reading list by category:
   - **module spec** — `docs/modules/implementation.md`
   - **contract spec** — `docs/contracts/implementation.md` (+ `docs/contracts/index.md`)
   - **logging-plugin spec** — `docs/logger/implementation.md` + the "Per-Graph Custom Logging" section of `docs/harness/logging.md`
   - **schema spec** (`01`/`01a`/`01b`/`01c`) — no harness doc loads these serde dataclasses; cite the rtl_buddy `config/*.py` source, the `@serde` idiom in `docs/modules/implementation.md`, and `02-payload-conventions.md` (the canonical type / `is_pass()` table). All four share `modules/rtl_test/schema/`.
   - **graph/manifest spec** (`11`) — `docs/harness_configs/graph.md`, `docs/harness_configs/plugin_manifest.md`, `docs/harness_configs/rtl_comrade_config.md`, `docs/harness/validation.md`, and `06-graph-yaml.md` (the design source it copies verbatim)
   - **end-to-end spec** (`12`) — `docs/running.md` + `docs/testing.md` + `rtl_buddy/AGENTS.md` (validation section)
   - **thin parent indexes** (`04`–`10`) and `specs/README.md` — **exempt** (navigation, not buildable units; each child ticket carries its own reading list).
3. Every link must resolve inside this repo.

> **Logging-plugin specs (resolved by TODO #31, 2026-06-11):** step 2 originally named only
> "module" and "contract" categories. Logging-plugin specs (`specs/10c`) are a third category,
> now folded into step 2 above with the reading list `docs/logger/implementation.md` + the
> "Per-Graph Custom Logging" section of `docs/harness/logging.md`. `specs/10c` already carries
> this `## Before you start`; apply the same to any future logging-plugin spec.

### 31. Bring the logging-plugin spec (10c) to the same buildable standard

**Status: Resolved (2026-06-11).** All three steps done. **Plugin form revised the same day:**
the spec was first brought to standard as a `SummaryHandler` (`logging.Handler`) + paired
`drop_summary_events` processor, then redesigned as a **single stateful `SummaryProcessor`**
(structlog processor) once it was recognised that the handler was a workaround for the missing
processor-finalisation hook. The redesign **assumes that harness gap is closed** (see
[07 item 27](implementation-test/07-ambiguities-and-assumptions.md)). The processor accumulates
**results only** — `git_state` falls through to the console. Net state of the three steps:

1. **`## Surface` section added to
   [`specs/10c`](implementation-test/specs/10c-summary-handler.md)**: the build-view skeleton
   (`class SummaryProcessor` with `__call__` appending `test_result` to `self._rows` and raising
   `DropEvent`, returning every other event — incl. `git_state` — unchanged; `finalise`
   rendering the `key`/`result`/`desc` table, a no-op on empty `self._rows`). No separate
   `drop_summary_events` — the one processor accumulates and drops. Labelled build view with
   [05 — The `SummaryProcessor` logging plugin](implementation-test/05-branching-and-results.md#the-summaryprocessor-logging-plugin)
   as the design view (same split as TODO #18).
2. **Wiring-surface block** added in place of the module I/O block: what it accumulates
   (`test_result`) vs passes through (`git_state` and all else), chain position (before
   `ConsoleRenderer`), teardown hook (`finalise()`, per-run), registration (the `logging` block
   in [`graphs/test.yaml`](implementation-test/06-graph-yaml.md) by `path`/`name`, **not** a
   module manifest).
3. **TODO #20 gap closed**: step 2 now names logging-plugin specs as a third reading-list
   category (`docs/logger/implementation.md` + the "Per-Graph Custom Logging" section of
   `docs/harness/logging.md`); the forward-reference blockquote under TODO #20 is updated to
   reflect the fold-in. `specs/10c`'s existing `## Before you start` already resolves to both.

The original ticket text is kept below for the record (it predates the processor redesign and
still names the handler form).

Mirror TODOs #18, #19, and #20 for [`specs/10c-summary-handler.md`](implementation-test/specs/10c-summary-handler.md)
— the one buildable ticket that produces a **logging plugin** (`SummaryHandler` +
`drop_summary_events`) rather than a graph module. TODOs #18/#19 inlined a `## Surface`
(skeleton + I/O block) into every *module* spec but explicitly skipped 10c, because a
`logging.Handler` has no `run()`/ports; TODO #20's reading-list step 2 names only "module"
and "contract" specs, not logging plugins. The net effect is that 10c is the lone buildable
ticket without an inline skeleton — the exact flip-between-files problem TODOs #18/#19 set out
to remove, just for a different artefact kind.

#### Concrete steps

1. Add a `## Surface` section to 10c, shaped for a logging plugin rather than a module: the
   `class SummaryHandler(logging.Handler)` skeleton (`emit(self, record)` collecting
   `test_result`/`git_state` rows into `self._rows`/`self._git_state`; `finalise(self)`
   rendering the git stateline + `key`/`result`/`desc` table, a no-op when `self._rows` is
   empty; drives no exit code) and the `drop_summary_events(logger, method_name, event_dict)`
   processor signature (raises `structlog.exceptions.DropEvent` on `test_result`/`git_state`).
   The sketches already live in
   [`05 — The SummaryHandler logging plugin`](implementation-test/05-branching-and-results.md#the-summaryhandler-logging-plugin)
   — inline them as the *build view*, with 05 as the *design view* (same split as TODO #18).
2. In place of the module I/O block, add a small **wiring surface** block: the events consumed
   (`test_result`, `git_state`), the teardown hook (`finalise()` via `App.cleanup`), how it is
   registered (the `logging` block in [`graphs/test.yaml`](implementation-test/06-graph-yaml.md)
   by `path`/`name`, **not** a module manifest), and the handler-ordering invariant (added
   after `LoggingFatalHandler`, so it never observes `CRITICAL`).
3. Close the TODO #20 gap: amend TODO #20 step 2 to name logging-plugin specs as a third
   category whose reading list is `docs/logger/implementation.md` + the "Per-Graph Custom
   Logging" section of `docs/harness/logging.md`. 10c already carries this `## Before you
   start` — confirm it resolves, and apply the same to any future logging-plugin spec.

#### Acceptance check

`specs/10c` carries an inline skeleton + wiring-surface block matching the buildability of the
module specs (a reader can build the plugin without opening `05` or the catalog), and TODO #20's
reading-list rule explicitly covers logging plugins.

### 21. Inline file path and manifest entries in each spec

**Status: Resolved (2026-06-11).** Every bare `Manifest entries per [06]` reference in `specs/` is
replaced with the exact `modules/config.yaml` addition inlined into the spec (verbatim from
[06](implementation-test/06-graph-yaml.md)). Concretely:

- **Per-module child tickets** (`03`, `04a`–`04i`, `05a`–`05f`, `06a`–`06b`, `07a`–`07b`,
  `08a`–`08f`, `09a`–`09c`, `10a`, `10b`) each carry a `**Manifest**` block with the single
  `- { name: …, class_name: …Mod }` line for that module, naming the `- file: rtl_test/<file>.py`
  block it joins. The `.py` target file path is already stated at the head of each Deliverables
  section. `03-run-process.md` had no manifest line at all — one was added.
- **Shared-file forward references** (concrete-step 3): the four `modules/config.yaml` file blocks
  are each shared across specs, so every block names its *opener* and its *appenders*.
  `rtl_test/setup.py` is opened by [`04a`] and appended by `04b`–`04i` / `05a`–`05f` / `10b`;
  `rtl_test/build.py` opened by [`06a`], appended by `06b` / `07a` / `03` / `07b`;
  `rtl_test/sim.py` opened by [`08a`], appended by `08b`–`08f` / `09a`–`09c`;
  `rtl_test/control.py` is a single-entry block (`10a`). Opener tickets show the `- file:` header;
  appenders show only the indented plugin line with an "append, don't re-create" note.
- **Index specs** (`04`–`10`) carry the consolidated file-block view for their children, flagging
  which sibling chains append to the same block.
- **Assembly spec** (`11`) inlines the full `modules/config.yaml` (all four blocks) and the
  `contracts/config.yaml` `any` entry, so the manifest-owner spec is self-contained too.
- **Non-manifest entries** left as explicit non-manifest notes: `10c` (`SummaryProcessor` — a
  logging plugin referenced by `path`/`name`, not a manifest) and `02` (already inlined the
  `contracts/config.yaml` `any` block). No `serial_acquire` contract exists (removed by TODO #30).

The original ticket text is kept below for the record.

Specs currently say "Manifest entries per [06]" — the implementer must open `06-graph-yaml.md` to find the manifest line for each module. Move the exact additions into the spec.

#### Concrete steps

1. For each module spec, state the target file path explicitly (e.g., `File: modules/rtl_test/sim.py`).
2. Include the exact YAML to append to `modules/config.yaml` (and the contracts manifest where relevant).
3. If the file is shared across specs, name which earlier spec creates it and which later specs append to it (see TODO #26, forward-reference notes).

#### Acceptance check

A reader can build and register the module without opening any file other than the spec.

### 22. Expand each module's algorithm into numbered implementation steps

**Status: Resolved (2026-06-11).** A dedicated `## Algorithm` section was added to every
module/contract/plugin spec, placed after `## Surface` and before `## Deliverables`, narrating
the skeleton as numbered steps with **each reachable failure path as its own numbered step**
(not a parenthetical aside) — concrete steps (1)/(2)/(3). Coverage: the 31 per-module child
tickets (`04a`–`04i`, `05a`–`05f`, `06a`–`06b`, `07a`–`07b`, `08a`–`08f`, `09a`–`09c`,
`10a`–`10c`), the `any` contract (`02` — an `## Algorithm — get_inputs()` for the scheduling
loop), and the `SummaryProcessor` plugin (`10c` — `__call__` / `finalise`). Spec `03`
(run-process) already carried an exhaustive `## Lifecycle` section that serves this role and was
left as-is. The inline `**Behaviour:**` numbered lists previously in `04b`/`04f`/`04g` were
folded into the new section to remove duplication. Out of scope: the schema specs (`01`,
`01a`–`01c`, which declare serde dataclasses/getters, not module algorithms) and the
non-module assembly/end-to-end specs (`11`, `12`).

One knock-on design gap surfaced while writing the algorithms and was resolved (your call):
- **`write-randseed` `HierInstanceSeed.txt` (08d).** rtl_buddy appends `HierInstanceSeed.txt`
  to the `.randseed` only when `'hier_inst_seed' in run_cmd` (the sim argv), but
  `WriteRandseedMod` is a `keyed_join` that never received the argv. Decision: carry the full
  `argv` on the `sim_cmd` keyed port (`build-sim-cmd`, [08c](implementation-test/specs/08c-build-sim-cmd.md))
  so the join node runs the membership check itself (`keyed_join` cannot take a persistent
  input). Spec 08c surface/skeleton/deliverables and 08d skeleton/algorithm/deliverables/tests/
  acceptance updated to match.

The original ticket text is kept below for the record.

Implementation prose is currently one-liner bullets. Anything with branching, file I/O, exception handling, or multi-step state changes should be a numbered step list.

#### Concrete steps

1. For each non-trivial module, expand the implementation prose into numbered steps.
2. Each step is one paragraph: what to do, what to read/write, what to emit.
3. Failure paths get their own steps — not parenthetical asides.

### 23. Add a "Constraints" section to every spec

**Status: Resolved (2026-06-11).** A `## Constraints` foot section was added to every
module/contract/plugin spec, phrased as imperatives per concrete step (3) and covering the three
content dimensions of step (2): numeric ranges/literals/format widths
(`random.randrange(1_000_000)` upper-bound-exclusive, `_TIMEOUT_GRACE_S = 5.0`,
`default_timeout = 60`, `max_levels = 8`, per-tag `run.{test_tag}.f`), the **failure idiom** each
site follows (`log.critical` vs unwired `result` port + `log.error` at emission vs propagate-uncaught
vs no-log routing — cross-referenced to [05 — Log idioms](implementation-test/05-branching-and-results.md#log-idioms-per-failure-site)),
and the **harness invariants** honoured (single-source-per-port, string-literal port names so
`definite_emits` holds, no graph awareness / emit on the deliberately-unwired terminal ports,
and `EndSentinel` propagation where it is the module's concern — the `any` contract). Placement:
after `## Acceptance criteria`, before `## Notes` where present (08b's pre-existing one-bullet
Constraints was expanded to the same fuller shape).

Scope (confirmed with the user, 2026-06-11): the literal "every spec" reading was adopted —
all 31 per-module child tickets (`04a`–`04i`, `05a`–`05f`, `06a`–`06b`, `07a`–`07b`, `08a`–`08f`,
`09a`–`09c`, `10a`–`10c`), the `any` contract (`02`), `run-process` (`03`, whose
Signal/timeout-policy + `rc=4444` subsections were distilled into a foot recap rather than left
inline-only), the four schema specs (`01`, `01a`–`01c`, where the constraints are the rename /
fresh-copy / raise-vs-critical / side-effect invariants), and the two assembly/e2e specs (`11`,
`12`, where the constraints are assembly-level "copy 06 verbatim; no fan-in/agg; no serial_acquire;
unwired ports are `no_destination` not errors" and parity-validation rules). The parent index
files (`04`–`10`) and `specs/README.md` are pure navigation and were left out. This is a wider
scope than TODO #22's (which excluded `03`/schema/assembly) — the user's call.

The original ticket text is kept below for the record.

Specs need a foot section enumerating what the implementer must NOT do, plus invariants the code must hold. Currently constraints are inferred from prose or from the parent design files.

#### Concrete steps

1. Add a `## Constraints` section at the foot of each module spec.
2. Include: numeric ranges (`random.randrange(1_000_000)`, not `1_000_001`); the failure idiom the module follows (port-routed vs `log.error` vs `log.critical` — see TODO #2, failure integration); harness invariants the module honours (single-source-per-port, EndSentinel propagation, no graph awareness).
3. Phrase as imperatives: "Use…", "Do not…", "Failure on X must…".

### 24. Enumerate test cases with input/expected pairs

**Status: Resolved (2026-06-11).** Every module/contract/plugin spec's `## Tests` section now
enumerates cases in `<input> → <expected output>` form, one per bullet, per concrete step (1).
Each section covers the three dimensions of step (2) — **every reachable output port** (e.g.
`keep`/`skip`, `ok`/`fail`, `default`/`fail`), **every failure mode** (the `log.critical`/
`log.error`/propagate-uncaught idiom per site, cross-referenced to the spec's Algorithm), and
**boundary values** (zero/empty, inclusive window edges, missing/malformed files, default
args, tag-regex sanitisation) — and **names the harness fixture** per step (3):
`run_module_scenario`/`run_contract_scenario`, `tmp_path` + `monkeypatch.chdir`/`setenv`,
`capsys`, mock-`subprocess`, `logging_handler` (for the `failure`/`pytest.raises(SystemExit)`
assertions), and `PortTestInput` for the `any` contract's blocking-await branch. The
acceptance bar (≥4 enumerated cases, or all reachable ports plus boundary inputs, whichever is
larger) is met in every touched spec.

Scope (confirmed with the user, 2026-06-11):
- **The 31 per-module child specs** (`04a`–`04i`, `05a`–`05f`, `06a`–`06b`, `07a`–`07b`,
  `08a`–`08f`, `09a`–`09c`, `10a`–`10c`) — all expanded from their 1–2 happy-path bullets.
  Trivial classifiers (`05a` route-list-mode, `09a` route-post) reach the bar with an
  empty-payload / `is not None`-vs-truthiness boundary case rather than padding.
- **The `any` contract (`02`)** — gained a top-level `## Tests` section in
  `run_contract_scenario` `port_inputs → expected_outputs` form. Its previously buried test
  list (a `### contracts/tests/test_any.py` block *inside* Deliverables) was promoted here and
  the Deliverables subsection trimmed to a pointer, so there is one source of truth; the stress
  (≥13 ports) and `hypothesis` property tests are retained.
- **run-process (`03`)** — gained a `## Tests` section enumerating one case per terminal
  Lifecycle state (normal/non-zero/signal exit, timeout→`rc=4444`, SIGQUIT→SIGKILL escalation,
  organic-4444 `timed_out` independence, launch-failure `log.critical`, cancellation with no
  `proc` emit), driven by `await run_module_scenario` with shell-child doubles. Its expectations
  previously lived only as probes in Acceptance criteria.
- **Assembly (`11`) and end-to-end (`12`)** — gained `## Tests` sections: `11` enumerates
  graph-load / `validation.py` (no cycles / no overloaded inputs / `no_destination` at INFO) /
  `--help` checks plus a removed-node regression guard; `12` enumerates the five CLI parity
  scenarios against the real reference suite as `invocation → parity-with-rtl_buddy` cases.

Left as already-compliant (the user's call): the three schema specs (`01a`/`01b`/`01c`) already
carry rich enumerated `## Tests` sections well past four `<input> → <expected>` cases
(round-trip, every YAML rename, resolution-order tables, validation `ValueError`s, result
freshness) — no rework. Out of scope: the shared-schema index (`01`, no module tests), the
parent index files (`04`–`10`) and `specs/README.md` (pure navigation, no `## Tests`).

The original ticket text is kept below for the record.

Tests sections currently list 1–2 bullets per module covering the happy path. Each module should enumerate cases explicitly.

#### Concrete steps

1. Expand each module's Tests section to list cases in `<input> → <expected output>` form, one per bullet.
2. Cover: every named output port hit at least once; every failure mode; every boundary value (zero, max, missing, malformed).
3. Name any harness fixture used (test-double for a contract, mock subprocess for `run-process`, etc.).

#### Acceptance check

Every module has at least four enumerated test cases, or all reachable output ports plus boundary inputs, whichever is larger.

### 25. Spell out filename and format placeholders

**Status: Resolved (2026-06-12).** Audited every `specs/` file for filename/format
placeholders. The load-bearing offenders were the log/randseed naming placeholders
`logs/<test>[_NNNN].log` (`04g`) and `f"{logs_dir}/{test_name}[_{run_id:04d}]…"`
(`08b`, `08c`) — the `[…]` brackets hid both the padding width and the conditionality of the
run-id suffix. All are now spelled out as an explicit rule with an example expansion: the
suffix is `""` when `ctx["run_id"] is None`, else `f"_{run_id:04d}"` (run-id zero-padded to four
digits), so e.g. `logs/my_test.log` for a single run and `logs/my_test_0003.randseed` for run-id
3. Each site now cites the authoritative format source — rtl_buddy `_get_log_path`
(`tools/vlog_sim.py:82-86`), verified against the source (pairs with TODO #16). `04g` additionally
disambiguates the two legs: the compile leg names files off the **sanitised** `test_tag`
(`_get_build_tag`, `vlog_sim.py:61-65`), the sim leg off the **raw** `test_name`. The `test.*`
symlink shorthand is left as-is where it is overview/index prose pointing at `08e` (which spells
`test.log`/`test.err`/`test.randseed` in full), but expanded inline in `12`'s acceptance artefact
list. Remaining `<…>` tokens (`builder="<name>"` in `04e`, `obj_dir_<tag>/` in `04f` prose) are
config values / shorthand, not filename-format placeholders, and are spelled out at their real use
sites (`07a`'s `obj_dir_{test_tag}`).

The original ticket text is kept below for the record.

Specs use placeholders like `[_NNNN]` and `<test>` that hide exact format details (padding width, file extensions, hidden-file conventions). Where the format matters, spell it out with an example expansion.

#### Concrete steps

1. Audit each spec for placeholders in filename conventions, padding patterns, and format strings.
2. Replace with explicit format specifiers (e.g., `:04d` zero-padding) paired with an example (`test_0003.randseed`).
3. Where the format is set by rtl_buddy, cite the rtl_buddy line that defines it (paired with TODO #16, source traceability).

### 26. Add forward-reference notes between specs that share a file

**Status: Resolved (2026-06-12).** Each shared Python file's `## Before you start` note in
`specs/` was made directional, matching the pattern the **Manifest** sections already used for
`modules/config.yaml`:

- **Creating specs** ([`04a`](implementation-test/specs/04a-discover-config-file.md) → `setup.py`,
  [`06a`](implementation-test/specs/06a-run-preproc.md) → `build.py`,
  [`08a`](implementation-test/specs/08a-expand-runs.md) → `sim.py`) now say "**creates** … the
  file then receives further additions from <appending specs>" (previously they wrongly said
  "appends to").
- **Appending specs** (30 specs total across the three groups, incl. `03` which appends to
  `build.py`) now say "appends to `<file>`, which is created by spec [N] — append, do not
  overwrite", then list the rest of the sharers.
- **Sole writers** ([`02`](implementation-test/specs/02-any-contract-and-fan-in.md) `any.py`,
  [`10a`](implementation-test/specs/10a-early-stop-gate.md) `control.py`,
  [`10c`](implementation-test/specs/10c-summary-handler.md) `summary.py`) state they are the
  sole writer (`10c` added per this todo; `02`/`10a` already did). The schema specs
  (`01`/`01a`/`01b`/`01c`) share the `schema/` **package** but write separate files — already
  noted.
- [`specs/README.md`](implementation-test/specs/README.md) gained a **Shared files** section
  with the create/append table (incl. the `config.yaml` manifest and per-group test files).

The original ticket text is kept below for the record.

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

### 32. Decide and add "Before you start" reading lists for the non-module/contract/logging specs

**Status: Resolved (2026-06-11).** Reading lists decided for every remaining category and the
sections added; TODO #20 step 2 now names a reading list (or exemption) for every spec category.

- **Schema specs** (`01`, `01a`, `01b`, `01c`): no harness doc loads these serde dataclasses —
  the section cites the rtl_buddy `config/*.py` source each spec already names (anchored
  `v1.4.0`), the `@serde` idiom in `docs/modules/implementation.md`, and
  `02-payload-conventions.md` (the canonical type / `is_pass()` table the port must match), and
  records that all four share the `modules/rtl_test/schema/` package.
- **Graph / manifests** (`11`): cites `docs/harness_configs/graph.md` (incl. its "Logging
  configuration" section), `docs/harness_configs/plugin_manifest.md`,
  `docs/harness_configs/rtl_comrade_config.md`, `docs/harness/validation.md`, and
  `06-graph-yaml.md`; notes it is the sole owner of the files it assembles.
- **End-to-end** (`12`): cites `docs/running.md`, `docs/testing.md`, and the already-referenced
  `rtl_buddy/AGENTS.md` validation section.
- **Thin parent indexes** (`04`–`10`) and **`specs/README.md`**: **exempted** — they carry no
  buildable work (navigation only; each child ticket carries its own reading list). The
  exemption is recorded in TODO #20 step 2 rather than adding a placeholder section.

All cited links resolve inside the repo. The original ticket text is kept below for the record.

TODO #20 added a `## Before you start` reading list to every **module**, **contract**, and
**logging-plugin** spec. Its step 2 only ever defined reading lists for those three categories,
so the remaining specs were left without one — and, unlike the three resolved categories, there
is no obvious doc to name. This ticket is to decide the reading list for each remaining category
and then add the section, the same way TODO #31 had to fold the logging-plugin category into
step 2 before `specs/10c` could be filled.

Specs still missing the section, by category:

- **Schema specs** — `01-shared-schema`, `01a-builder-schema`, `01b-suite-schema`,
  `01c-model-schema`. Candidate reading list: the harness config/serde docs the dataclasses
  mirror (`docs/harness_configs/index.md` + the relevant child) and the rtl_buddy
  `config/*.py` types they mirror.
- **Graph / manifests** — `11-graph-and-manifests`. Candidate: `docs/harness_configs/graph.md`
  + the modules/contracts manifest docs.
- **End-to-end test** — `12-end-to-end`. Candidate: `docs/testing.md` + the end-to-end harness
  docs.
- **Thin parent indexes** — `04`–`10`. **First decide whether index files need the section at
  all** (they carry no implementation work — they only link to children). If yes, the natural
  content is a pointer to the children's reading lists, not a duplicate.
- **`specs/README.md`** — almost certainly excluded (it is the spec index, not a spec), but
  record the exclusion explicitly so the rule is closed.

#### Concrete steps

1. For each category above, decide the reading list (or that the category is exempt) and amend
   TODO #20 step 2 to name it — mirroring the logging-plugin fold-in done by TODO #31.
2. Add the `## Before you start` section to each non-exempt spec, after `Depends on:` /
   `References:` and before `## Goal`, matching the wording/placement of the module and contract
   specs.
3. Every link must resolve inside this repo.

#### Acceptance check

Every `specs/*.md` either carries a `## Before you start` section or is explicitly recorded as
exempt, and TODO #20 step 2 names a reading list for every spec category.

## Cosmetic

### 28. Pin the module file-layout and package conventions

`06-graph-yaml.md` suggests grouping modules into `setup.py`, `build.py`, `sim.py`, `control.py` (also implicit in `specs/04-setup-modules.md:13` → `modules/rtl_test/setup.py`). This is described as a "suggestion" rather than a pinned layout, leaving the package shape ambiguous.

#### Concrete steps

1. Commit to a package name (`modules/rtl_buddy/`) and the final file grouping (which module goes into which file).
2. Record the mapping in `06-graph-yaml.md` (or a new section in `specs/README.md`).
3. Pin the plugin manifest namespace (e.g., `rtl_buddy:derive-seed-mode`) so modules cannot collide with sibling graphs.

#### Acceptance check

Every module spec names exactly one file path, and that file path matches the committed layout.

### 29. Clarify the dataflow diagram

The ASCII diagram in `00-overview.md` mixes main-line and config edges; the layout is visually congested and a few branches collapse into the same column. The node table in `04-pipeline-and-contracts.md` compensates, but a clearer diagram would help reviewers trace the graph at a glance. Consider switching to a Mermaid diagram.

#### Concrete steps

1. Split the existing diagram into two: main-line dataflow only; config / persistent-input edges only.
2. Consider producing a graphical version (mermaid, or generated from `06-graph-yaml.md`).
3. Cross-reference both diagrams from the node table in `04-pipeline-and-contracts.md`.

#### Acceptance check

A reviewer can trace any single edge type without visual conflict from another.

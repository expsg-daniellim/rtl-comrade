# implementation-test todos

Todos for bringing the `implementation-test/` plan to a buildable, internally consistent state. Items are grouped into three sections by priority:

- **Design-level** — open questions, unresolved decisions, and structural gaps that must be settled *before* per-spec polish is meaningful. Most of these correspond to items in `implementation-test/07-ambiguities-and-assumptions.md` under "Open", "Deferred (KIV)", and "To verify against the framework before building"; cross-references appear inline as `07` item *N*.
- **Spec polish** — patterns that need to be applied to each `specs/` ticket so that an implementer can build a module from the spec alone, without flipping between catalog, design files, and rtl_buddy source.
- **Cosmetic** — small structural improvements; not blocking.

Items are numbered globally for cross-referencing (e.g., "see TODO #5"). The order within each section reflects rough priority but is not load-bearing — items in the same section can be picked up in parallel where dependencies allow.

> **Note on file:line citations.** All file/line references in this document are anchored to commit `9308c86` at todo-creation time. Re-verify line numbers against the current state of the source files before acting on a citation.

## Design-level — must resolve before building

### 1. Enumerate failure modes — and resolve open questions sitting in build tickets

Several `specs/` tickets contain unresolved design questions phrased *as* spec prose. The clearest example is `specs/08-sim-cycle-modules.md:24-26` for `ResolveSeedMod`'s REPLAY-missing path:

> "on missing/invalid file, emit a `result` envelope with `SimTimeoutResults`-style FAIL? — actually per [03] writes a FAIL stub log + symlinks (verify against rtl_buddy `VlogSim.execute` REPLAY-missing path)."

A build ticket should never contain a question the implementer cannot answer from the ticket alone. This is upstream of every other todo in this file — none of the per-spec polish below is meaningful until specs are actually answerable.

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

`07-ambiguities-and-assumptions.md:146` notes `obj_dir`, `logs/`, and CWD-based artefacts are all CWD-relative — same as rtl_buddy. `07` item 17 defers per-invocation subdirs to an upstream rtl_buddy change. But structural concurrency is the design's whole advantage over rtl_buddy, and running two compiles or two sims in parallel will collide on `run.f`, `obj_dir`, `test.*` symlinks, and `rtl_buddy.log`. With no interim plan, the graph is effectively single-threaded.

#### Concrete steps

1. Pick an interim posture, explicitly: (a) wait for the upstream change and document the graph as single-threaded until then; (b) add a serialising contract on the compile/sim chain that enforces one-at-a-time within a suite; or (c) introduce per-key tempdirs at the graph level (e.g., `obj_dir/<key>/`).
2. If (a): add a constraint in `01-cli-and-entry.md` ("workers clamped to 1 until upstream lands"), and record the dependency.
3. If (b) or (c): write a design note and spec for the new contract or tempdir scheme. Identify which modules need to be aware (`link-latest`, `write-randseed`, anything CWD-touching).
4. Cross-link the chosen posture from `07-ambiguities-and-assumptions.md` item 17.

#### Acceptance check

Any reader can answer "what happens if two tests run in parallel?" without the entire answer being "the upstream change."

### 4. Validate the `MergeContract` design before downstream specs depend on it

`05-branching-and-results.md:98-99` identifies `MergeContract` as the only piece of genuine scheduling the design adds. `07` items 19–20 acknowledge that its concurrency safety is asserted, not proven. Eight terminal-result branches converge on `agg` through it (`04-pipeline-and-contracts.md` row 22); if it is wrong, every branch is wrong.

#### Concrete steps

1. Write a formal description: state held across `get()` calls, how `EndSentinel` propagates from each upstream port, behaviour on a key whose branch has already terminated, and the contract's overall termination rule.
2. Add a stress test: concurrent emissions from 8 mock upstreams with overlapping keys; assert no items lost, no duplicates emitted, and termination once all upstreams sent `EndSentinel`.
3. Add a property-based test if feasible: random `(key, port, payload)` interleavings produce a deterministic output set.
4. Once stabilised, document the contract in `docs/contracts/index.md` as a first-class shipped contract — not an `rtl_test`-private artefact.

#### Acceptance check

`MergeContract`'s correctness is supported by enumerated tests and a written invariant, not by intuition.

### 5. Finalise `run-process` async + signal semantics

`07` item 23 flags the SIGQUIT-to-process-group + `rc=4444` + `asyncio.wait_for` interaction as tricky and unfinalised. `run-process` is shared by compile and sim; if its semantics drift, both legs misbehave.

#### Concrete steps

1. Specify the timeout path explicitly: which signal is sent (`SIGTERM`/`SIGQUIT`/`SIGKILL`), to whom (process or process group), with what grace period before escalation.
2. Define the `rc=4444` sentinel: when it appears, what it means, who sets it, who reads it. Match rtl_buddy's convention.
3. Specify `asyncio.wait_for` cancellation cleanup — orphan subprocess handling, file-handle closure for redirected stdout/stderr, partial-output preservation guarantees.
4. Add explicit failure cases to `specs/03-run-process.md`: subprocess killed externally; subprocess exits before `wait_for` schedules its wake-up; subprocess never reaps.

#### Acceptance check

`specs/03-run-process.md` documents the lifecycle from `popen` to either `rc=int` or `rc=4444` with no hand-wave, and is testable against a slow-sleep fake.

### 6. Document framework-verification contingencies

`specs/00-framework-verification.md` is a probe-first spec — it verifies `**kwargs` port inference, persistent-without-edge handling, and `keyed_join` payload unwrap before any module is built. But there is no documented decision tree for what to do if any probe *fails*. The fallback for `aggregate-results.run(**fired)` (eight explicit `=None` ports) is mentioned in passing but not written out. (The same probes are tracked as items 19, 21, 22 in `07-ambiguities-and-assumptions.md` under "To verify against the framework before building".)

#### Concrete steps

1. For each probe in `specs/00-framework-verification.md`, add an "If this fails, …" section that names the fallback design and identifies which downstream specs need to change.
2. For `**kwargs` port inference: pre-write the eight-explicit-port version of `aggregate-results` (signature + body sketch) and place it in the spec as the standby.
3. For persistent-without-edge: identify which CLI defaults (`run_ids`, `reg_level`, `start_level`) rely on this and pre-design the workaround (explicit constant-emitter nodes, or sentinel edges).
4. For `keyed_join` payload unwrap: identify alternative payload shapes that work even if the contract delivers tuples instead of unwrapped values.

#### Acceptance check

Running `specs/00-framework-verification.md` produces either a green light or a written fallback plan — never an open question.

### 7. Pin the interim CWD strategy

`08-sibling-graphs.md:135` drops `chdir-suite` "on the assumption" the upstream per-invocation-subdir change lands first. The plain `test` graph already relies on CWD-based artefact placement (`link-latest` writes symlinks "in CWD"; multiple modules write to `logs/...`). Until the upstream change lands, the design silently assumes someone `cd`s into the suite directory before invocation. The CLI entry path does not say so. (See `07-ambiguities-and-assumptions.md` "Implementation notes" — "CWD assumptions preserved" — for the explicit acknowledgement; the deeper concurrency story is `07` item 17.)

#### Concrete steps

1. Decide: does `rtl_comrade test` `cd` automatically to a derived directory (e.g., `<suite_dir>`), or must the user do so before invocation?
2. If automatic: add a small `chdir-suite` module (the one named in the dropped design) and wire it into the test graph, not only the regression sibling.
3. If user-driven: add a startup check that fails fast if CWD is outside the suite directory.
4. Update `01-cli-and-entry.md` to record the convention.

#### Acceptance check

`01-cli-and-entry.md` answers "where do I invoke `rtl_comrade test` from?" without ambiguity.

### 8. Prepend `.` to `$PATH` for CWD-local tool discovery

`07-ambiguities-and-assumptions.md` "Implementation notes" records that rtl_buddy prepends `.` to `$PATH` so a CWD-local simulator (`simv`, `verilator`) is discoverable. The note says `run-process` "or a setup node like `resolve-builder`" must replicate it. No current spec captures the behaviour, and skipping it breaks tool discovery in the common rtl_buddy invocation pattern.

#### Concrete steps

1. Decide which module owns the `$PATH` mutation: `run-process` (per-subprocess) or `resolve-builder` (one-shot during setup). Decide once; do not duplicate.
2. Record the chosen owner in `03-module-catalog.md` and in either `specs/03-run-process.md` or `specs/04-setup-modules.md`.
3. Add a test: a subprocess invocation through the chosen module resolves a `.`-relative binary that is not on the inherited `$PATH`.
4. Promote the implementation note from "informational" status to a settled item in `07-ambiguities-and-assumptions.md` once the owner is chosen.

#### Acceptance check

The chosen module's spec explicitly mentions the PATH-prepend behaviour, and a test exercises it.

### 9. Define the `builder_cfg` / `RtlBuilderConfig` schema

`resolve-builder`, `filter-reglvl`, `build-compile-cmd`, `resolve-seed`, `build-sim-cmd`, and `write-filelist` all consume a `builder_cfg`/`builder_mode` value (`03-module-catalog.md:47,210,225`; `04-pipeline-and-contracts.md:98`). The shape — fields, types, methods like `get_seed()` — is implicit. `02-payload-conventions.md` does not pin it. (`07-ambiguities-and-assumptions.md` item 1 settles that the YAML config schema is preserved drop-in; the Python types that load it are the implementer's responsibility.)

#### Concrete steps

1. In `specs/01-shared-schema.md`, declare the `RtlBuilderConfig` dataclass (or equivalent) with every field used downstream — at minimum `seed`, `unames`/platform map, the compile/sim/post command shapes, defaults.
2. Declare the methods used by modules (`get_seed()` and others) as members of the class or as free functions over it.
3. Add a `Source:` citation to the rtl_buddy `RtlBuilderConfig` class (paired with the source-traceability todo, TODO #16).
4. Update each downstream module's spec to reference the schema by field, not by guess.

#### Acceptance check

Any module consuming `builder_cfg` can be written without opening rtl_buddy to discover field names.

### 10. Pin the `tests.yaml` and `models.yaml` schemas

`parse-suite-config` reads `tests.yaml` and deserialises "into the schema (spec 01)" (`specs/04-setup-modules.md:24`); `load-model` later reads `models.yaml`. Neither schema is committed to in `specs/01-shared-schema.md` or `02-payload-conventions.md`. (As with TODO #9, `07-ambiguities-and-assumptions.md` item 1 settles that the YAML surface is preserved drop-in but does not name the Python types.)

#### Concrete steps

1. In `specs/01-shared-schema.md`, declare `SuiteConfig`/`TestConfig`/`ModelConfig` dataclasses with every field consumed downstream — at minimum `name`, `model`, `timeout`, `regression_level`, `sweep`, `plusdefines`, `plusargs`, `preproc`, `uvm`.
2. Add `Source:` citations to the rtl_buddy dataclass definitions.
3. State which fields are required vs optional, and the default for each optional.
4. Update each consumer module spec (`select-tests`, `filter-reglvl`, `load-model`, `expand-sweep`, `run-preproc`, `build-compile-cmd`, `build-sim-cmd`, `parse-uvm-log`) to reference the schema by field.

#### Acceptance check

Any consumer module can be written from the spec without reading rtl_buddy source for field names.

### 11. Verify persistent-but-unwired CLI defaults

`07` item 21 flags that `run_ids`, `reg_level`, and `start_level` are persistent inputs on `resolve-seed`/`filter-reglvl` but have no edges in the plain `test` graph — the design relies on Python defaults activating. Whether the harness allows a persistent input port to be unwired (with a default kicking in) is an unverified behavioural assumption.

#### Concrete steps

1. Add a probe to `specs/00-framework-verification.md` that explicitly tests an unwired persistent input: does the contract fire the module with the default, or does validation reject the graph as missing an edge?
2. If validation rejects: design either (a) explicit constant-emitter nodes for each default, or (b) sentinel "run-with-default" edges.
3. If validation accepts but the module never fires: same fallback.
4. Update `06-graph-yaml.md` to wire the chosen approach.

#### Acceptance check

The plain `test` graph passes validation and `resolve-seed`/`filter-reglvl` fire with the intended defaults.

### 12. Specify `logs/` directory ownership and lifecycle

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

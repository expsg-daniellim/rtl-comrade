# Comparison: `test-implementation/` vs `implementation-test/`

Two independent plans for porting `rtl_buddy test` functionality as an `rtl_comrade` graph. This document records the strengths and weaknesses of each, then a head-to-head comparison.

---

## Plan A — `test-implementation/`

### Structure and organisation

- Master document (`rtl-comrade-test-graph-module-plan.md`, ~1900 lines) plus 23 numbered per-feature specs (`00-artefacts.md` … `22-git-status.md`) plus `README.md`.
- Each spec is templated and self-contained: prerequisites, rtl_buddy source-line references, code skeletons, registry update, test list, constraints.
- README provides ordering table, file-grouping rationale (which specs share a Python file), and an explicit "artefacts vs observability" distinction.
- Master plan §7 sequences work into four executable slices (skeleton → compile → sim → post), each with a concrete validation target.

### Strengths

- **Traceability to rtl_buddy.** Every spec cites the legacy source lines it must mirror (e.g. `vlog_sim.py:L211-L245` in 14-seed-resolve.md).
- **Parcelability.** Numbered slicing into 22 specs makes work easy to distribute; README marks independent vs sequential specs.
- **Seed handling is exhaustive** (specs 02, 13, 14): priority order, run-id zero-padding (`_0003`), replay file lookup, `1000000` upper bound, all three modes' inter-relations.
- **Result-row vocabulary unified** (spec 19, master §6.27): every failure branch emits `TestResultRow` directly. The originally-planned `ResultNormalize` hub is explicitly removed because it would have violated single-source-per-port — and the plan *says so* in the doc.
- **Termination via `EndSentinel`** through the `continue` port of `RunDepthGate` (spec 10) is correctly identified as automatic — the gate does not signal anything, sentinel propagation handles it.
- **Exit-code policy** (spec 20, master §6.30) lists exactly which modules must call `log.error`, with `SKIP` carved out.
- **`RunDepthGate` reuse**: one module with three instance configs at three depths, with a duck-typed `instance_key` property contract on the three artefact types. Clever and well documented.
- **"Artefacts vs observability" framing** in the README is unusually thoughtful.

### Weaknesses

- **Drift between master plan and per-spec files.** Master plan §6.1 and §10 keep a `CliArgsMerge` node and `cli-args-source`; spec 21 explicitly removes them in favour of direct CLI edges into consumer nodes. Master plan was not retrofitted. Two competing topologies sit in the same directory. `TestCliArgs` is similarly inconsistent (defined in master §4, absent from spec 00).
- **Citation bugs.** README and several specs link to `docs/module-implementation.md` / `docs/contract-implementation.md`; the actual paths are `docs/modules/implementation.md` and `docs/contracts/implementation.md`.
- **Undefined contract names.** Specs throughout reference `latest` and `unit` contracts. The harness ships `DefaultContract`, `zip`, `group_until_end` — `latest`/`unit` are not defined in the plan or harness docs and need aliasing or remapping.
- **Missing `@serde` decorators.** Spec 10 (and others) omit `@serde` on nested `Config` classes. `docs/modules/implementation.md` deserialises through `serde.from_dict(...)`, which requires the decorator. Will cause runtime failures.
- **Hand-waved load-bearing details:**
  - Spec 11 references `preprocessed.test.model_path_parent`, which is not a field on `TestConfigEnvelope`.
  - Spec 11 reads `models.yaml` without specifying its schema (rtl_buddy has `ModelConfig`; not ported or specified).
  - Specs 11, 14, 15 reconstruct builder config from a dict but the dict shape is not defined.
- **Inconsistent failure idiom.** Some specs say `log.critical + SystemExit(1)`; others just say "fatal." Per invariants, `CRITICAL` already triggers `SystemExit(1)`.
- **`RegressionLevelSkipFilter` cardinality.** Master §6.9 says "emit one SKIP row for each run id"; spec 06 emits a single row with `run_id=None`. Harmless for plain `test` (one run id) but diverges for regression.
- **`PreprocessedRunPlan` embedded inside `FilelistArtefact` and `CompileResult`** to reduce edges; the plan flags this deliberately, but it tightly couples artefacts that could otherwise have used default-valued ports.
- **`git-status`** has no downstream edge in master §10; spec 22 acknowledges but does not resolve.
- **Four near-identical envelope types** (`RunPlan`, `PreprocessedRunPlan`, `PerRunExecutionPlan`, `ResolvedRunPlan`), each adding one field — boilerplate.

---

## Plan B — `implementation-test/`

### Structure and organisation

- Top-level briefing tree (`00-overview.md` … `08-sibling-graphs.md`) — design narrative.
- Downstream `specs/` directory with 13 sequential implementation tickets (`specs/00-framework-verification.md` … `specs/12-…`), each with explicit `Depends on:` and `Acceptance criteria` blocks.
- `specs/README.md` lists which tickets can run in parallel.
- Module catalogue (`03-module-catalog.md`) enumerates 27 modules with `In/Out/Contract/Tags` plus a `Module → rtl_buddy provenance` table.
- Reads as a *design memo*, not a checklist — the reasoning is preserved.

### Strengths

- **Architectural discipline.** §2 of `00-overview.md` ("Atomic modules; coordination in contracts") forbids guards or graph-awareness in modules. Early exits are *named output ports* (`skip`, `stop`, `fail`, `timeout`), never flags inside a payload.
- **Branches-as-ports throughout.** No module has a guard. The fan-in collector `aggregate-results` does no scheduling; scheduling lives in a new `merge` contract.
- **Payload conventions** (`02-payload-conventions.md`): three clear shapes (`ctx`, work, `result`). The rule "`ctx` never carries a `result`" prevents the envelope creep that rtl_buddy's `RootConfig`/`TestConfig` god-objects had.
- **Termination** is traced node by node in `04-pipeline-and-contracts.md` ("Liveness / termination"); sentinel handling in the new `merge` contract is sketched in `05`.
- **Honest unknowns.** `07-ambiguities-and-assumptions.md` splits items into **Settled / Open / Deferred (KIV) / To verify / Notable divergences / Implementation notes**. Names the unknowns rather than glossing them.
- **Probe-first discipline.** `specs/00-framework-verification.md` is the *first* implementation ticket — verify harness assumptions (`**kwargs` port inference, persistent-without-edge, `keyed_join` payload unwrap) *before* building.
- **Provenance table** at the foot of `03-module-catalog.md` gives one-glance correspondence to rtl_buddy source.
- **Sibling extensions are clean** (`08-sibling-graphs.md`): `randtest` adds 1 module; `regression` adds 2 modules + a contract switch. `parse-suite-config` is the same module paired with different contracts in different graphs — best demonstration of the harness/contract split paying off.
- **Genuine improvement over rtl_buddy.** `run-process` redirects to caller-supplied files instead of buffering through `PIPE` — partial output survives timeouts, memory bounded.
- **Compile and sim share `run-process`.** One module, instantiated twice. Direct expression of "compile and sim are the same primitive."
- **CLI mapping is exact** (`01-cli-and-entry.md`): one-for-one against `rtl_buddy.py` flags, with deliberate drops (`--debug`, `--color`) called out.

### Weaknesses

- **Concurrency is the largest gap.** `07` item 17 defers the per-invocation-subdir story to a "deferred upstream rtl_buddy change." Until that lands, `run.f`, `obj_dir`, `test.*` symlinks, and `rtl_buddy.log` collide if two compiles or two sims run concurrently. The plan acknowledges this honestly but does not propose an interim serialising contract — the design's whole point (vs rtl_buddy) is structural concurrency, so this is load-bearing.
- **`run-process` async semantics** are flagged in `07` item 23 as not finalised — SIGQUIT-to-process-group + `rc=4444` + `wait_for` interaction is acknowledged tricky but only sketched.
- **`aggregate-results.run(**fired)`** relies on `**kwargs` port inference the harness may not support. Fallback (eight `=None` params) is mentioned but not written out.
- **`MergeContract` correctness** is asserted, not proven; `07` items 19/20 acknowledge.
- **`VlogPost` quirks** (`07` item 15) left as open.
- **ASCII dataflow diagram** in `00` mixes main-line and config edges; some branches collapse visually. The node table in `04` compensates, but a graphical version would help.
- **`run_ids`, `reg_level`, `start_level`** are persistent-but-unwired for plain `test`, relying on Python defaults — `07` item 21 calls this out as needing verification.
- **Some module file-layout suggestions** (`setup.py`, `build.py`, `sim.py`, `control.py`) are sketched only as suggestions.

---

## Head-to-head

### Where Plan A is better

- **Traceability to legacy code.** Plan A cites rtl_buddy source line ranges in every spec; Plan B has one provenance table.
- **Implementation depth per area.** Plan A's specs include code skeletons and detailed test lists. Plan B's `specs/` are leaner — they assume the design files have done the heavy lifting.
- **Seed handling is more thoroughly specified** in Plan A (priority order, padding, replay lookup, 1M bound).
- **Exit-code policy** is enumerated module-by-module in Plan A. Plan B describes the principle (`log.error` from `finalise()`) but not the per-module list.
- **Parcelability.** Plan A's specs are smaller and more independent — easier to assign in parallel without context conflicts.

### Where Plan B is better

- **Architectural discipline is named and centred.** Plan B states "branches-as-ports, re-convergence as contract" as a guiding principle in `00-overview.md` §2 and references it throughout. Plan A applies the same principle in practice (the `ResultNormalize` removal is the strongest example; `RunDepthGate` with `continue`/`stop` ports is another) but does not name it as a unifying rule. Both plans use the same "one gate module, three instances at depth boundaries, port routing not guards" shape (Plan A's `RunDepthGate` / Plan B's `early-stop-gate`).
- **Honest unknowns.** Plan B's `07-ambiguities-and-assumptions.md` is the single most valuable artefact in either plan. Plan A leaves unknowns (the `latest`/`unit` contract names, `models.yaml` schema, builder-config dict shape) buried in individual specs rather than surfacing them.
- **Probe-first.** Plan B opens implementation with framework-verification. Plan A jumps straight to building.
- **Internal consistency.** Plan B has one canonical topology. Plan A's master plan and spec 21 are mutually inconsistent on `CliArgsMerge` and `TestCliArgs`.
- **Payload hygiene.** Plan B's `ctx`/work/`result` three-shape rule is principled; Plan A's four near-identical envelope chain is boilerplate.
- **Sibling graph extensibility.** Plan B's `08-sibling-graphs.md` shows the design extends to `randtest`/`regression` with minimal churn (1–3 new modules). Plan A only addresses `test`.
- **Substantive improvements over rtl_buddy** (file-redirected `run-process`, compile/sim as one module reused).
- **Smaller surface area.** Plan B's 27 modules vs Plan A's larger node count (master plan §10) means fewer things to validate.

### Common weaknesses

- Both rely on harness features they have not pre-verified (`**kwargs` port inference, persistent-without-edge handling). Plan B at least makes this a probe spec; Plan A does not.
- Both treat `models.yaml` / filelist resolution lightly compared to its real complexity in rtl_buddy.
- Both depend on contract behaviour (`latest`/`unit` in Plan A; the new `MergeContract` in Plan B) that the harness does not yet ship cleanly.

### Risks if implemented as-written

- **Plan A** will produce code in the wrong shape in several places: undefined contract names, missing `@serde`, inconsistent `CliArgsMerge` references, hand-waved `models.yaml`. Some of this is recoverable mid-build; the `CliArgsMerge` drift will cause real confusion.
- **Plan B** will produce code with the right shape but will hit the framework-verification step and may need to backtrack on `**kwargs` port inference, the `MergeContract` design, and concurrency. The plan is up-front about this.

### Bottom line

Plan A is more thorough on legacy behaviour and per-feature detail; Plan B is more thorough on architecture, unknowns, and harness-fit. Plan A is the better *checklist*; Plan B is the better *design memo*. The strongest path forward is probably to use Plan B's structure (design narrative + probe-first specs + ambiguities file) as the spine and lift Plan A's per-feature traceability (rtl_buddy source-line citations, seed-handling exhaustiveness, exit-code enumeration) into Plan B's `specs/` tickets.

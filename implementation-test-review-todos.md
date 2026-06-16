# implementation-test review todos (second list)

Findings from a full review pass over `implementation-test/` (all eight parent docs `00`–`08`
plus every `specs/` ticket), cross-checked against the actual `rtl_buddy` v1.4.0 source
(`a69d962`) and the `rtl-comrade` harness docs under `docs/`. These are **separate** from the
`#1`–`#32` items in `implementation-test-todos.md` (all of which are resolved); numbered `R1`,
`R2`, … to avoid cross-reference clashes.

Grouped by priority:

- **Critical** — contradictions or gaps that would block a faithful build or break rtl_buddy
  parity if each spec is implemented exactly as written.
- **Consistency / doc-sync** — drift left behind by the TODO #15/#30 redesign that was not
  propagated into the per-module specs or the canonical payload doc; cheap to fix, but a builder
  coding to the stale text would produce the wrong shapes.
- **Minor** — local nits in individual specs.

> **Note on citations.** File/line references are anchored to the spec state at review time
> (working tree on `master`, after commit `98484b1`). Re-verify before acting.

> **Common root cause.** The design docs (`02`, `05`, `10`) were revised by TODO #15 (summary →
> logging plugin; terminal ports unwired) and TODO #30 (per-tag naming), but the revisions did
> not fully reach the per-module `specs/` tickets or `02-payload-conventions.md`.

---

## Critical — must resolve before building

### R1. Terminal result rows never reach the summary — two distinct gaps (collection + success-path emission)

**Status: Resolved (2026-06-15).** Implemented across the spec tree:

- **Direct-log on the otherwise-silent paths:** `parse-log` (`09b`), `parse-uvm-log` (`09c`), and
  `filter-reglvl.skip` (`05d`) now log one `test_result` event per verdict — `log.error` on
  non-`is_pass()` (drives the exit), `log.info` on pass-like. (This also resolves R2 for the
  parse-NA case; the early-stop NA exit question remains under R2.)
- **Watch-list collection:** `SummaryProcessor` (`10c`) gained a `Config` (`events` watch-list +
  `suppress` subset). Default `events` = `test_result` plus the failure terminals'
  `compile_failed`/`sim_timeout`/`load_model_failed`/`sweep_failed`/`preproc_failed`/
  `filelist_failed`/`replay_seed_invalid`; default `suppress` = `["test_result"]` (failure errors
  stay on the console).
- **Failure terminals enriched, not duplicated:** `07b`/`08f`/`05e`/`05f`/`06a`/`06b`/`08b` add
  `result`/`desc` kwargs to their **existing** `log.error(...)` — no parallel `log.info`.
- **Canonical docs synced:** `02` Shape 3, `05` (processor sketch + log-idiom tables), `00`, `03`,
  `04` updated to the two-style emission + watch-list model. Stale `test_failed` /
  `parse_log_read_failed` events removed (only intentional "no separate … event" negations remain).

`02-payload-conventions.md` (Shape 3) and `05-branching-and-results.md` (Re-convergence; "Every
terminal site … additionally emits `log.info("test_result", …)`") require every terminal site to
feed the summary, and `10c`'s `SummaryProcessor` renders the table *solely* by matching
`event_dict["event"] == "test_result"`. There are **two separate problems**:

**(a) Collection is hard-coded to one event name.** `SummaryProcessor.__call__` matches only the
literal `"test_result"`. Of the 13 terminal sites, **only `early-stop-gate` (`10a`) emits that
event.** The failure terminals emit differently-named events that the processor ignores:

- `interpret-compile` (`07b`): `log.error("compile_failed", …)`
- `interpret-sim` (`08f`): `log.error("sim_timeout", …)`
- `parse-log`/`parse-uvm-log` (`09b`/`09c`) on FAIL: `log.error("test_failed", …)`
- `load-model`/`expand-sweep`/`run-preproc`/`write-filelist`/`resolve-seed`
  (`05e`/`05f`/`06a`/`06b`/`08b`): `log.error("…_failed", …)`

So `SummaryProcessor` should keep a **configurable watch-list of event names** (supplied via its
`Config` — processor classes support a `Config`, per `docs/logger/implementation.md`) and harvest
`key`/`result`/`desc` from each, rather than hard-coding `"test_result"`. **The watched events are
the ones the terminals already emit** (`compile_failed`, `sim_timeout`, the five `*_failed`, and
early-stop's event) — so closing this half is *wiring the watch-list*, **not** adding new log
calls. Those events currently carry `rc`/`stderr_path`/`log` but not `result`/`desc`, so enrich
each terminal's **existing** `log.error(...)` kwargs (from the `TestResults` the module already
builds) — or have `SummaryProcessor` derive the verdict from the event name. Either way: no
parallel `log.info` is added.

**(b) The success paths emit no event at all — PASS (and SKIP) rows never reach the logging
flow, and there is no node to carry them there.** This is independent of (a): no event-name
configuration can collect an event that was never logged.

- `parse-log` (`09b`) / `parse-uvm-log` (`09c`): on **PASS** (and on NA) they only
  `return ("default", {key, result})` and **log nothing** — `log.error("test_failed", …)` fires
  *only* on the non-pass branch. So a passing test produces no log event whatsoever; the result
  is emitted on the (unwired) `default` port but never enters the logging flow the summary reads.
- `filter-reglvl` skip (`05d`): returns `("skip", {key, result: SkipResults})` with **no log
  call**, so SKIP rows are likewise invisible to the summary.

Fix: make `parse-log` / `parse-uvm-log` (and `filter` on skip) **emit their verdict directly** as
a `test_result` log event — `log.error("test_result", key, result, desc)` when `not
result.is_pass()`, else `log.info("test_result", …)` — the same pattern `early-stop-gate` (`10a`)
already uses. The one call both feeds the summary (`SummaryProcessor` already watches
`test_result`) and, at ERROR level on a non-pass verdict, drives the exit code (failure-flagging
lives outside the formatter chain, so a `DropEvent` of the console line doesn't affect it). It
folds the existing `test_failed` / `parse_log_read_failed` logs into that single emission. **No
new module, no graph rewiring; the ports stay unwired.** Because `SummaryProcessor` already
collects `test_result`, the parse/skip half is closed entirely in `09b`/`09c`/`05d` — no `10c`
change is needed for it.

Net effect as written today: the rendered table would contain **only early-stop rows** — every
PASS, SKIP, FAIL, timeout, and compile-fail is missing — contradicting `10c`'s acceptance ("table
content matches what `aggregate-results.finalise()` produced") and `12`'s parity assertion.

#### Concrete steps

1. **(b) parse/skip — log directly:** in `09b`/`09c`/`05d`, emit one `test_result` event per
   verdict — `log.error("test_result", key, result, desc)` if `not is_pass()` else
   `log.info("test_result", …)` — folding the existing `test_failed`/`parse_log_read_failed` logs
   into it. No new module; ports stay unwired; `SummaryProcessor` collects `test_result`
   unchanged. (This is the `early-stop-gate` pattern, and it also resolves R2 for the parse-NA
   case: NA → `not is_pass()` → ERROR → exit 1.)
2. **(a) Failure terminals — watch-list:** give `SummaryProcessor` a `Config` watch-list so it
   *also* collects the events the failure terminals already emit (`compile_failed`, `sim_timeout`,
   `load_model_failed`, `sweep_failed`, `preproc_failed`, `filelist_failed`, `replay_seed_invalid`)
   in addition to `test_result`. For each, append a row; `DropEvent` only the summary-only
   `test_result` rows so they don't double-print — the failure `log.error`s keep printing.
3. **Enrich, don't duplicate (failure terminals):** make those watched failure events carry
   `key`/`result`/`desc` by adding the kwargs to each terminal's **existing** `log.error(...)`
   (from the `TestResults` it already builds), or have `SummaryProcessor` map event-name →
   verdict. **No parallel `log.info`** on terminals that already log.
4. Update `09b`/`09c`/`05d` (direct logging), `10c` (the `Config` watch-list for the failure
   events), and the `03`/`05` log-idiom tables. Port counts and graph wiring are **unchanged**.

#### Acceptance check

A run over the reference suite renders one summary row per terminal item — PASS, SKIP, FAIL, NA,
timeout, compile-fail — matching the `N×M×R` count in `04`; `SummaryProcessor`'s watched event set
is config-driven (not a hard-coded `"test_result"`); the otherwise-silent paths
(`parse-log`/`parse-uvm-log`/`filter.skip`) log `test_result` directly; and the failure terminals
carry `result`/`desc` on their existing `log.error` (no parallel `log.info`, no new module, no
graph rewiring).

### R2. Early-stop (and parse-NA) exit-code semantics are self-contradictory and break parity

**Status: Resolved (2026-06-15).** Decision: `--early-stop` is a **user-provided flag**, so
stopping because of it is a successful exit, **not** a failure → Plan B exits **0** (deliberately
diverging from rtl_buddy's exit 1). Recorded as a deliberate divergence rather than chasing parity
(option 3 of the concrete steps). The parse-NA half was already closed via R1 (genuine NA →
`log.error("test_result")` → exit 1, which is retained). Changes:

- **Divergence recorded** in `07` ("Notable divergences from rtl_buddy" gains an `--early-stop`
  exits-0 bullet; item 10 notes early-stop as the one non-contributing NA).
- **`02`** table: `stop` (`gate-*`) row → exit 0; `is_pass()`-source-of-truth note carves out the
  early-stop exception; direct-`test_result` bullet notes early-stop always uses `log.info`.
- **`05`** Result-aggregation prose drops early-stop from the exit-1 list; log-idiom table note
  for `early-stop-gate.stop` replaced the "see review R2" placeholder with the settled divergence.
- **`specs/10`** acceptance carves out the early-stop exit-0 exception; **`specs/10a`** gains a
  deliberate-divergence note (its `log.info`/no-`log.error` skeleton was already correct).
- **`specs/12`** parity scenarios: `--early-stop` now asserts exit 0 (documented divergence) with
  per-test `NA` + `desc` parity retained; the other four scenarios keep full exit-code parity.

Original analysis below.



Confirmed against `rtl_buddy/src/rtl_buddy/runner/test_results.py`: `EarlyStopResults` has
`result='NA'`, and `is_pass()` is true only for `PASS`/`SKIP`. So rtl_buddy's
`exit_code |= 0 if is_pass() else 1` (`rtl_buddy.py:206`) **exits 1 on `--early-stop`** and on
any **NA** verdict.

Plan B's exit code is driven *solely* by per-emission `log.error` (Settled item 10). The two
descriptions disagree:

- `10a` (early-stop-gate) emits **no `log.error`** ("a stop is a normal terminal, not a
  failure"), and `05-branching` lists early-stop under "no `log.error`".
- But `02`'s table says `EarlyStopResults` → **exit 1**; `10`'s index acceptance says "a run
  with any **FAIL/NA** emits ≥1 `log.error` → harness exit 1"; and `12` asserts exit-code parity
  for `--early-stop`.

So `10a` contradicts `10`'s own index, `02`'s table, and rtl_buddy. As written, Plan B exits
**0** on `--early-stop`; rtl_buddy exits **1**.

The **same NA contradiction is in `parse-log` (`09b`)**: its skeleton does
`if not result.is_pass(): log.error(...)` (fires for NA), but its Algorithm/Constraints/Tests
say "PASS/NA does not log." `09c` inherits the wording.

#### Concrete steps

1. Decide the intended exit semantics for NA terminals (early-stop + parse NA). For rtl_buddy
   parity it must be **exit 1** → the NA terminal must `log.error` (in addition to its
   `test_result` row from R1).
2. If parity is intended: update `10a` (early-stop must `log.error`), and fix `09b`/`09c`
   prose+tests to match their skeletons (NA logs). Update `05-branching`'s "non-failure
   terminals" table accordingly (early-stop moves out of the no-error bucket).
3. If exit-0-on-early-stop is actually wanted: record it as a **deliberate divergence** in `07`,
   fix `02`'s table (early-stop → exit 0), and fix `10`'s index acceptance ("any FAIL/NA → exit
   1") and `12`'s parity claim.
4. Either way, reconcile `02` table ↔ `05` log-idiom tables ↔ `09b`/`09c`/`10a` ↔ `10`/`12`
   acceptance so all five agree.

#### Acceptance check

`rtl-comrade test --early-stop <phase>` and an NA-verdict test produce the same exit code as
`rtl_buddy` (per `12`), and `02`/`05`/`09`/`10` state one consistent rule for NA.

### R3. Root-config schema (`spec 01`) is under-specified; `resolve-builder`/`select-platform` read undefined attributes

**Status: Resolved (2026-06-15).** Verified against `rtl_buddy/src/rtl_buddy/config/root.py` +
`platform.py` (`a69d962`). Two design decisions taken: builder lookup uses **option (b)** (wire
`root_cfg` into `resolve-builder`), and **verible is dropped entirely** (pyserde silently ignores
the unknown `cfg-verible`/`verible` keys — confirmed empirically — so files still load drop-in).
Changes:

- **`spec 01`** brought to 01a/b/c depth: new "§ `root.py` schema (detailed)" with field tables
  for `RootRtlField`, `RootConfigFile`, `PlatformConfigFile`, and the runtime **`RootConfig`**
  (now an explicit deliverable — a thin wrapper over `RootConfigFile` that precomputes
  `rtl_builder_cfgs`, mirroring `root.py:94`). `VeribleConfigFile`/`VeribleConfig` and the runtime
  `PlatformConfig` removed from deliverables; `cfg-verible` dropped from the rename list;
  constraints/acceptance updated (drop-in load incl. ignored verible keys; `RootConfig` exposes
  `platforms`/`rtl_builder_cfgs`/`cfg_rtl_reg`).
- **`04e` (`resolve-builder`)** rewired to `run(root_cfg, platform_cfg, builder="")`:
  `name = builder or platform_cfg.builder`; `builder_cfg = root_cfg.rtl_builder_cfgs.get(name)`.
  Skeleton/algorithm/deliverables/tests/constraints all updated (the bogus
  `platform_cfg.default_builder`/`platform_cfg.builders` removed).
- **`04d`** goal clarified (emits the raw `PlatformConfigFile`, no `initialise`); **`04c`** notes
  `RootConfig(raw)` is the precompute-the-dict wrapper.
- **`06`** new edge `parse-root → resolve-builder.root_cfg` (consistent with existing root_cfg
  fan-out; `unit` joins multiple inputs — precedent: `ensure-logs`). **`04`** pipeline table S4
  row + fan-out summary updated. **`03`** catalog `resolve-builder` In/Source/log idiom updated.
- **`07`** new "Notable divergences" bullet recording verible-drop + builder re-homing.

Original analysis below.



Traced against `rtl_buddy/src/rtl_buddy/config/root.py` + `platform.py`. In rtl_buddy the
builders dict (`cfg-rtl-builder` → `{name: RtlBuilderConfig}`) lives on **`RootConfig`**, and a
platform resolves a **single** builder via `PlatformConfigFile.initialise(builders, veribles,
override)`, returning a `PlatformConfig` whose `builder` is one `RtlBuilderConfig` — there is no
`builders` dict and no `default_builder` on a platform.

Plan B's specs assume a different, never-defined shape:

- `04c` constructs `RootConfig(raw)`, but **`spec 01` never lists `RootConfig`** as a deliverable
  (only `RootConfigFile`), and — unlike `01a`/`01b`/`01c` — gives **no field tables, methods, or
  renames** for the `root.py` types.
- `04d` (`select-platform`) reads `root_cfg.platforms` and `platform_cfg.unames` and emits the
  matched platform **without calling `initialise`** (forwards a raw object).
- `04e` (`resolve-builder`) reads `platform_cfg.default_builder` and
  `platform_cfg.builders.get(name)` — **neither attribute exists**, and `06`'s edge list never
  wires the root builders dict into `resolve-builder` (it receives only `platform_cfg` + CLI
  `builder`). As written, the node cannot look up a builder.

This is the largest "not sufficient as an implementation" gap.

#### Concrete steps

1. Bring `spec 01` to the same depth as `01a`/`01b`/`01c`: full field tables + renames +
   methods for `RootConfigFile`, the runtime **`RootConfig`** (explicitly listed as a
   deliverable), `PlatformConfigFile`, and the runtime `PlatformConfig`.
2. Decide and document where the root `cfg-rtl-builder` list becomes a `{name:
   RtlBuilderConfig}` dict, and how `resolve-builder` obtains it. Two clean options:
   (a) `select-platform` calls a Plan-B `initialise` that attaches the builders dict +
   configured builder name to the emitted `platform_cfg`; or (b) wire `parse-root`'s builders
   dict into `resolve-builder` as a second input and add that edge to `06`.
3. Reconcile `04d`/`04e` skeletons with the chosen model — replace `platform_cfg.default_builder`
   / `platform_cfg.builders` with the actually-defined attributes/inputs.
4. Note that verible resolution (rtl_buddy `platform.initialise` also resolves/criticals on
   verible) is intentionally dropped in Plan B, and mark `VeribleConfigFile`/`VeribleConfig` in
   `spec 01` as unused-but-loaded (or drop them).

#### Acceptance check

A reader can implement `parse-root-config` → `select-platform` → `resolve-builder` from `spec
01` + `04c`/`04d`/`04e` alone, and `resolve-builder` has a defined source for the builder it
looks up. Round-trip against `../rtl-buddy-proj-template/.../root_config.yaml` passes.

---

## Consistency / doc-sync

### R4. `02-payload-conventions.md` is stale in three payload shapes and one contract

**Status: Resolved (2026-06-15).** Verified the canonical shapes against `03` (run-process Out
port), `07a`, `08c` (working tree after `98484b1`):

- **`02` Shape 2** updated — `command` → `{key, argv, stdout_path, stderr_path}`; `proc` →
  `{key, rc, timed_out, stdout_path, stderr_path}` (redirect-to-file design, no in-memory
  `stdout`/`stderr` bytes); `sim_cmd` gains `argv` (carried for `write-randseed`'s
  `hier_inst_seed` membership check).
- **`merge` contract removed** — `02` Sentinels now states the test graph's contracts are
  `unit`/`default`/`keyed_join` (+ unwired `any`) with no `merge`; `08`'s Summary bullet ("No
  new contracts beyond `merge`") reworded to "No new contract types beyond those already in the
  test graph". Also fixed `05`'s stale chapter intro (results "re-converge through a custom
  contract" → collected by `SummaryProcessor`, ports unwired).

Original analysis below.

`02` is the canonical shape doc the specs point to, but:

- **`proc`** is given as `{key, rc, stdout: bytes, stderr: bytes, timed_out}`. Actual
  (`03` + downstream) is `{key, rc, timed_out, stdout_path, stderr_path}` — the redirect-to-file
  design. `interpret-compile` reads `proc["stderr_path"]`, absent from `02`'s shape.
- **`command`** is given as `{key, argv}`. Actual (`07a`/`08c`) is `{key, argv, stdout_path,
  stderr_path}`.
- **`sim_cmd`** is given as `{key, seed, log, err, randseed_path}`. Actual (`08c`/`08d`) adds
  `argv` (needed for the `hier_inst_seed` membership check).
- **`merge` contract** — `02` ("re-converge through the `merge` contract") and `08`'s Summary
  ("No new contracts beyond `merge` (already present in the test graph)") both reference a
  `merge` contract that does not exist; re-convergence was removed by TODO #15.

#### Concrete steps

1. Update `02` Shape 2 for `proc`, `command`, and `sim_cmd` to match `03`/`07a`/`08c`/`08d`.
2. Remove the `merge`-contract sentence in `02` (Sentinels section) and fix `08`'s Summary
   ("No new contracts beyond `merge`") — the test graph uses `unit`/`default`/`keyed_join`
   (+ unwired `any`); there is no `merge`.

#### Acceptance check

Every payload shape in `02` matches the dict each producing module emits; no doc references a
`merge` contract.

### R5. `exec_hook` helper has two contradictory signatures

**Status: Resolved (2026-06-15).** Settled on the 2-arg `exec_hook(path, namespace)` form —
confirmed against rtl_buddy's two analogues (`_expand_tests_with_sweep` `rtl_buddy.py:264-283`,
`VlogSim.pre` `vlog_sim.py:119-139`), which inline differing namespaces (sweep adds
`TestConfig` + `out_test_cfgs` and reads it back; preproc has neither). A fixed 3-arg
`(path, test, root_cfg)` can express neither, so the skeletons were the wrong side. Changes:

- **`05f`/`06a` skeletons** now build their own `ns` dict and call `exec_hook(path, ns)`
  (sweep then iterates `ns["out_test_cfgs"]`); Algorithm step 2 reworded to match.
- **Canonical definition once** in `05f` Notes: home `modules/rtl_buddy/_hooks.py` (private,
  not a graph-module file), signature `exec_hook(path, namespace) -> None` (read + `exec` into
  the caller's dict, returns nothing), and the **exception-propagation** contract (helper does
  **not** swallow like rtl_buddy; each caller's `try/except` routes the per-test FAIL).
- **`06a` + parent index `05`** now reference that single definition instead of restating it.

Original analysis below.

`05f`/`06a` skeletons call `exec_hook(path, ctx["test"], root_cfg)` (3 args),
but their Algorithm/Notes/Constraints describe the shared helper as `exec_hook(path, namespace)`
(2 args). Since sweep and preproc need *different* namespaces (sweep adds `TestConfig` +
`out_test_cfgs`; preproc does not), the 2-arg "caller builds the namespace" form is the right
design and both skeletons are misleading.

#### Concrete steps

1. Pick the `exec_hook(path, namespace)` form; update the `05f`/`06a` skeletons to build their
   own namespace dict and pass it (sweep reads `ns["out_test_cfgs"]` after).
2. State the helper's home (a private module in `modules/rtl_buddy/`) and its exact signature in
   one place that both specs reference.

#### Acceptance check

`05f` and `06a` show the same `exec_hook` call shape, and the helper signature appears once.

### R6. The "assume-closed harness gap" for processor `finalise()` is already satisfied

**Status: Resolved (2026-06-15).** Verified the hook is shipped:
`docs/logger/implementation.md:95-99` documents `finalise()` on **processors** (called by
`App.cleanup`, duck-typed), and `:165-167` gives the timing (before the failure check, not on a
`CRITICAL` exit). Reclassified from assumed-open gap to settled feature:

- **`10c`** — Depends-on line and Notes now state the hook is a shipped harness feature with the
  `:95-99` / `:165-167` citation, dropping "assumed available" / "assume-closed harness gap".
- **`07` item 27** — the "assumes that harness gap is closed" conclusion replaced with "the
  per-run finalisation hook already covers processors" + the doc citation; the historical
  handler-workaround framing is kept but past-tensed.

Original analysis below.

`07` item 27 and `10c` repeatedly frame the summary redesign as
*depending on an assumed-closed harness gap* (per-run processor finalisation). But
`docs/logger/implementation.md:95-99` shows the harness **already** calls `finalise()` on
processors (`App.cleanup` finalises processors then handlers, duck-typed, before the failure
check, not on CRITICAL) — exactly what `SummaryProcessor` needs. The assumption is met; the plan
text is stale in calling it open.

#### Concrete steps

1. Move the processor-`finalise()` assumption from "assume-closed gap" to **settled**, citing
   `docs/logger/implementation.md` (End-of-run finalisation with `finalise()` — processors).
2. Drop the hedging in `10c` ("Relies on … assumed available") and `07` item 27 ("assumes that
   harness gap is closed").

#### Acceptance check

`07`/`10c` state the processor-finalisation hook as a shipped feature with a doc citation, not
an open risk.

### R7. `spec 01` file-layout drifts from `01b` and `specs/README.md`

**Status: Resolved (2026-06-15).** Decision: keep `UVMConfig` in a **separate `uvm.py`**
(not inlined) — `parse-uvm-log` (`09c`) is effectively its only consumer; the rest of the
graph treats `TestConfig.uvm` as an opaque presence/absence flag. Reconciled all three docs to
that layout:

- **`01b`** Deliverables rewritten from "single `suite.py` with `UVMConfig` inlined" to two
  files — `uvm.py` (`UVMConfig` alone) and `suite.py` (`TestbenchConfig`/`TestConfigFile`/
  `TestConfig`/`SuiteConfigFile`/`SuiteConfig`, importing `UVMConfig` for the annotation); the
  `UVMConfig` subsection header notes its `uvm.py` home.
- **`spec 01`** deliverable bullet now names `suite.py` + a separate `uvm.py` with the
  one-consumer rationale.
- **`specs/README.md`** package-layout table + the shared-files "separate files" list now
  include `uvm.py`, plus the previously-missing `results.py` and `seed_mode.py`.

#### Acceptance check

`spec 01`, `01b`, and `specs/README.md` name the same set of schema-package files
(`builder.py`, `suite.py`, `uvm.py`, `model.py`, `root.py`, `results.py`, `seed_mode.py`).

---

## Minor

### R8. `spec 03` cites a retired spec 00

**Status: Resolved (2026-06-15).** `03`'s asyncio child-watcher note deferred default-policy
confirmation to "Spec 00's framework probe," but `specs/README.md` records spec 00 as retired
(2026-06-02). The empirical child-watcher check is actually already tracked under
[07 item 23](implementation-test/07-ambiguities-and-assumptions.md) (async subprocess hardening),
so the note now cites that item instead of the retired spec.

### R9. `05c` Deliverables prose drops `run_id` from `ctx`

**Status: Resolved (2026-06-15).** `05c`'s Deliverables prose now yields
`{"key": test.get_name(), "test": test, "run_id": None}`, matching the skeleton, Algorithm,
Tests, Constraints, and the canonical `ctx` shape in `02`.

### R10. `07a` (and `08c`) skeleton uses `plusdefines`/`plusargs` without constructing it

**Status: Resolved (2026-06-15).** `07a`'s skeleton appended `*plusdefines` (line ~53) but never
built the list (Algorithm step 2 does). On review **`08c` has the identical hole** — its skeleton
uses `*plusdefines, *plusargs` (line ~47) with neither built — so the original "fine in `08c`"
note was wrong; the two were already consistent with each other (both implicitly illustrative).
Fixed via the **mark-illustrative** route on both: each Surface section now states the skeleton is
illustrative and the Algorithm/Deliverables are authoritative for the elided list construction,
plus an inline `# … built per Algorithm step 2` comment at the `argv` line.

### R11. `08f` logs a "configured timeout" not present in `test_run`

**Status: Resolved (2026-06-15).** Fixed incidentally while enriching `08f`'s `log.error` for R1:
the `sim_timeout` event now carries `key`/`err`/`result`/`desc` (all present on `test_run`); the
"configured timeout" kwarg was dropped throughout `08f` (skeleton, algorithm, failure-handling,
tests, constraints).

### R12. `ensure-logs-dir` `_cwd` default weakens the CWD-sequencing guard

**Status: Resolved (2026-06-16) — fixed at the root via path-provenance centralisation.** The
original framing (note/assert that the `_cwd` edge must be present) treated a symptom. The root
problem was that artefact location was an *implicit global* (ambient CWD read inside each leaf's
`mkdir`/path-join), so `04g` needed a synthetic ordering-only `_cwd` token at all — and a
defaulted ordering-only port is exempt from edge-validation (Settled item 21).

Fix (design change, full centralisation): **path provenance is owned by one node; leaves consume
a resolved path.**
- **`check-suite-cwd` (`04f`)** now also emits `work_dir` (the validated base dir) — the single
  artefact-location source.
- **`ensure-logs-dir` (`04g`)** consumes `work_dir` as **load-bearing** data (`(Path(work_dir) /
  logs_dir).mkdir(...)`), so it is a required, non-defaulted port the harness edge-validates — the
  `_cwd` ordering token is gone and R12's "forgotten edge silently skips the guard" cannot
  happen. It emits the resolved directory `Path` on its `logs_dir` port plus the `env_ready`
  sequencing token.
- **The composers (`07a`/`08b`/`08c`)** take `logs_dir` as a resolved `Path` from `ensure-logs`
  and join filenames onto it — the CWD-relative assumption now lives only in the
  `check-suite-cwd → ensure-logs-dir` provider pair. `08d` already consumed a pre-composed path.
- Synced: `03` catalog rows, `06` graph edges (CLI `logs_dir` → `ensure-logs` only; resolved
  `logs_dir` Path fans out to the three composers; `check-cwd.work_dir → ensure-logs.work_dir`),
  `00` diagram, `04` pipeline tables/edge list, `07` settled item 26 + divergences, `04` index.

`run.f`/`obj_dir_<tag>/` remain CWD-relative (leaf-level) — extending the same provider model to
them is the natural next step, tracked under [07 item 17].

### R13. `make_fail_result` helper referenced in 7 skeletons but defined nowhere

**Status: Resolved (2026-06-15).** Found while sweeping the spec skeletons for the same
skeleton-vs-prose class as R10. `make_fail_result(desc=...)` is the generic per-test FAIL
constructor called from `05e`/`05f`/`06a`/`06b`/`08b`/`09b`/`09c`, but it appeared in **no**
deliverable, signature, or home — `results.py`'s inventory (`spec 01`) listed only the five
`TestResults` subclasses + base, none of which is a generic FAIL. Verified against
`rtl_buddy/src/rtl_buddy/runner/test_results.py`: the base `TestResults(results={...})` is
directly instantiable with an explicit verdict dict, and `VlogPost.get_results` builds plain
FAIL/NA that way (no dedicated subclass). Fix: gave the helper a home —

- **`spec 01`** `results.py` deliverable now defines
  `make_fail_result(desc: str) -> TestResults` (base `TestResults` with
  `{"result": "FAIL", "desc": desc}`) and names its seven consumers.
- **`02`** `TestResults` section points at it (canonical-doc cross-reference).

The parse-verdict shorthands (`scan_pass_fail`/`parse_uvm_summary`/`uvm_verdict`) were **not**
flagged — they are illustrative names for verdict logic the `09b`/`09c` Algorithm prose fully
specifies; `write_output` is fully documented in `06b`; `run_suffix`/`force_symlink`/`exec_hook`
each have a documented home.

### R14. Extend the `work_dir` provider model to `run.f` and `obj_dir_<tag>/`

**Status: Resolved 2026-06-16.** Follow-on to R12. The path-provenance centralisation (R12) covered
the artefact (`logs/`) tree only: `check-suite-cwd` emits `work_dir`, `ensure-logs-dir` roots
`logs/` on it and emits the resolved `Path`, and the composers join onto it. Two leaf-level writers
still composed **CWD-relative** paths and so still baked in the rtl_buddy "everything is
CWD-relative" assumption:

- **`run.f`** — `write-filelist` (`06b`) wrote `Path(f"run.{test_tag}.f")`, relative to the
  ambient CWD. **Now:** takes `work_dir` as a load-bearing persistent input and writes
  `Path(work_dir) / f"run.{test_tag}.f"`.
- **`obj_dir_<tag>/`** (and the verilator `simv = f"{build_dir}/simv"`) — `build-compile-cmd`
  (`07a`) composed `build_dir = f"obj_dir_{test_tag}"`, relative to the ambient CWD. **Now:** takes
  `work_dir` as a load-bearing persistent input and composes `build_dir = str(Path(work_dir) /
  f"obj_dir_{test_tag}")`; the verilator `simv` inherits the rooting via `build_dir`.

Both writers now consume `check-suite-cwd`'s `work_dir` directly (the same provider
`ensure-logs-dir` consumes), so location is decided once and a relocation (`--work-dir`,
regression's per-suite root) is a one-node change. **Residual (still item 17):** the non-verilator
`simv = builder_cfg.get_simv()` is a fixed configured name the graph can't redirect, plus the
`test.*` symlinks and tool-internal files — these wait on the per-invocation-subdir change
([07 item 17](implementation-test/07-ambiguities-and-assumptions.md)), which supersedes both the
per-tag naming and this `work_dir` rooting when it lands.

**Touch points (done):** `06b` (write-filelist), `07a` (build-compile-cmd `build_dir` / verilator
`simv`), the `03` catalog rows, `04f` (check-suite-cwd's `work_dir` consumer list), and `06` graph
edges (the `work_dir` fan-out to `filelist` / `cc-build`).

#### Acceptance check

`run.f` and `obj_dir_<tag>/` are composed by joining onto a provider-supplied base directory
(rooted on `work_dir`), not the ambient CWD; relocating all artefacts is a single-node change;
`07` item 17 + the "CWD assumptions preserved" note reflect that nothing leaf-level remains
CWD-relative.

---

## Index

| # | Title | Priority | Status |
|---|---|---|---|
| R1 | Summary collection hard-codes one event + PASS/SKIP paths emit nothing | Critical | Resolved 2026-06-15 |
| R2 | Early-stop / parse-NA exit-code semantics contradictory; break parity | Critical | Resolved 2026-06-15 (early-stop → exit 0 divergence; parse-NA via R1) |
| R3 | `spec 01` root schema under-specified; `resolve-builder` reads undefined attrs | Critical | Resolved 2026-06-15 (option (b) + verible dropped) |
| R4 | `02-payload-conventions` stale (`proc`/`command`/`sim_cmd` + `merge` contract) | Consistency | Resolved 2026-06-15 |
| R5 | `exec_hook` 3-arg skeleton vs 2-arg prose | Consistency | Resolved 2026-06-15 |
| R6 | Processor `finalise()` "gap" already satisfied by docs — reclassify settled | Consistency | Resolved 2026-06-15 |
| R7 | `spec 01` schema file-layout drift (`uvm.py`; `results.py`/`seed_mode.py`) | Consistency | Resolved 2026-06-15 (keep separate `uvm.py`) |
| R8 | `spec 03` cites retired spec 00 | Minor | Resolved 2026-06-15 |
| R9 | `05c` prose drops `run_id` from `ctx` | Minor | Resolved 2026-06-15 |
| R10 | `07a`/`08c` skeleton uses undefined `plusdefines`/`plusargs` | Minor | Resolved 2026-06-15 |
| R11 | `08f` logs a "configured timeout" absent from `test_run` | Minor | Resolved 2026-06-15 |
| R12 | `04g` `_cwd` default weakens CWD-sequencing edge validation | Minor | Resolved 2026-06-16 (path-provenance centralised: `check-cwd` `work_dir` → `ensure-logs` → composers) |
| R13 | `make_fail_result` referenced in 7 skeletons but defined nowhere | Minor | Resolved 2026-06-15 |
| R14 | Extend `work_dir` provider model to `run.f` / `obj_dir_<tag>/` (follow-on to R12) | Consistency | Resolved 2026-06-16 (`write-filelist`/`build-compile-cmd` take `work_dir`; non-verilator `simv` + symlinks remain for [07 item 17]) |

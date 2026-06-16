# Spec 09c: parse-uvm-log (`ParseUvmLogMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`ParseUvmLogMod`
reads `ctx["test"].uvm.max_warns` / `.max_errors` — `UVMConfig` lives in 01b).
**References:** [03 — Post-processing section](../03-module-catalog.md),
[07 settled 14, 15](../07-ambiguities-and-assumptions.md). Parent index:
[09 — Post-processing modules](09-post-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec
[`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle
modules (`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`,
index [09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Reimplement rtl_buddy's `UvmVlogPost.get_results()` to classify a UVM sim log from its
Report Summary severity counts.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   test_run
outputs:  default → result
```

```python
class ParseUvmLogMod:
    def run(self, test_run):
        uvm = test_run["test"].uvm
        try:
            text = Path(test_run["log"]).read_text()
            counts = parse_uvm_summary(text)         # missing summary → FAIL
            result = uvm_verdict(counts, uvm.max_warns, uvm.max_errors)
        except OSError as e:
            result = make_fail_result(desc=str(e))   # unreadable log → FAIL
        log_fn = log.error if not result.is_pass() else log.info   # ERROR drives exit on non-pass
        log_fn("test_result", key=test_run["key"],
               result=result.results["result"], desc=result.results["desc"])
        return ("default", { "key": test_run["key"], "result": result })
```

## Algorithm

1. Read the thresholds and log: `uvm = test_run["test"].uvm` (non-negative `max_warns` /
   `max_errors`, validated at deserialisation — not re-checked here); `text =
   Path(test_run["log"]).read_text()`.
2. Parse the UVM "Report counts by severity" block into WARNING/ERROR/FATAL counts. A missing
   Report Summary block is itself a FAIL ("Invalid UVM Report Summary"); `int()` over a
   regex-matched `[0-9]+` cannot raise.
3. Verdict: PASS iff `WARNING <= uvm.max_warns and ERROR <= uvm.max_errors and FATAL == 0`,
   else FAIL with the counts summary in `desc`.
4. **Log the verdict directly, then emit.** One `test_result` event:
   `log.error("test_result", key=, result=, desc=)` when `not result.is_pass()` (FAIL — the
   exit driver), else `log.info("test_result", ...)` (PASS); then return `("default", {"key":
   test_run["key"], "result": result})`. `SummaryProcessor` watches `test_result`; the `default`
   port stays unwired.
5. **Failure — unreadable log.** Wrap step 1's read in `try/except OSError` → build a FAIL
   `result` carrying `str(e)` as `desc` and fall through to step 4 (logged as an ERROR
   `test_result`). No separate `parse_uvm_read_failed` / `test_failed` event.

## Deliverables

In `modules/rtl_buddy/sim.py` (continuing from spec 08):

- `ParseUvmLogMod` — reimplements rtl_buddy `UvmVlogPost.get_results()` only: extract the
  UVM Report Summary "Report counts by severity" block; PASS iff `WARNING <=
  ctx["test"].uvm.max_warns and ERROR <= ctx["test"].uvm.max_errors and FATAL == 0`,
  else FAIL with the counts summary in `desc`. Both thresholds are `int` per spec
  [01b — `UVMConfig`](01b-suite-schema.md); their non-negative invariant is enforced
  at YAML deserialisation, so this module does not re-validate. Emits `{"key":
  ctx["key"], "result": TestResults(...)}`.
  **Failure handling**: the verdict is logged once as `test_result` — `log.error` when `not
  result.is_pass()` (FAIL; the exit driver), `log.info` when PASS (carrying `key`/`result`/`desc`).
  `FileNotFoundError`/`OSError` reading `test_run["log"]` → build a FAIL `result` with the
  exception string as `desc` and log it through the same `test_result` path. Missing Report
  Summary block is already a FAIL (explicit message); `int()` on regex-matched `[0-9]+` cannot
  raise `ValueError`. No separate `test_failed` / `parse_uvm_read_failed` event.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:58-81` — `UvmVlogPost.get_results`; thresholds from `UVMConfig` (`config/uvm.py:3-19`).

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: parse-uvm-log, class_name: ParseUvmLogMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `tmp_path` UVM log fixtures (varying Report
Summary counts; one without a summary block); a `test_run` whose `test.uvm` carries
`max_warns`/`max_errors`; `logging_handler` for the FAIL paths. Compare fixture-by-fixture
against rtl_buddy `UvmVlogPost`.

- Report Summary with `WARNING=0, ERROR=0, FATAL=0` within thresholds → emits `("default",
  {result: PASS})` and one `log.info("test_result", result="PASS", …)`; `failure is False`.
- `WARNING == max_warns` and `ERROR == max_errors`, `FATAL=0` → emits PASS (boundary:
  inclusive `<=` edge).
- `ERROR > max_errors` (others within bounds) → emits FAIL with the counts summary in `desc`
  and `log.error("test_result", result="FAIL", …)`; `failure is True`.
- `WARNING > max_warns` → emits FAIL, `log.error("test_result", …)`.
- `FATAL == 1` with WARNING/ERROR within thresholds → emits FAIL (boundary: `FATAL == 0` is
  absolute, not threshold-gated).
- Log with no Report Summary block → emits FAIL with `desc = "Invalid UVM Report Summary"`,
  `log.error("test_result", …)`.
- `test_run["log"]` missing → `OSError` caught → emits FAIL with `str(e)` in `desc`, logged as an
  ERROR `test_result`.

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: a fixture-by-fixture comparison against rtl_buddy
  `UvmVlogPost` on the same log files produces identical `TestResults`.
- Failure idioms exercised: a log with no UVM summary → a FAIL `result`; a missing
  `test_run["log"]` → `OSError` caught → FAIL with `str(e)` in `desc`. Every verdict is logged
  once as `test_result` — ERROR on FAIL (exit driver), INFO on PASS — which `SummaryProcessor`
  collects ([10c](10c-summary-handler.md)).
- The `modules/config.yaml` manifest entry `{ name: parse-uvm-log, class_name: ParseUvmLogMod }`
  validates and the harness resolves `parse-uvm-log` → `ParseUvmLogMod`.

## Constraints

- Verdict: PASS **iff** `WARNING <= max_warns and ERROR <= max_errors and FATAL == 0`; else FAIL
  with the counts summary in `desc`.
- A missing Report Summary block is itself a FAIL (`"Invalid UVM Report Summary"`).
- Do **not** re-validate the thresholds — their non-negative invariant is enforced at YAML
  deserialisation (spec [01b](01b-suite-schema.md)).
- Log the verdict once as `test_result`: `log.error("test_result", key, result, desc)` when
  `not is_pass()` (FAIL — the exit driver), else `log.info("test_result", …)` (PASS). Do **not**
  emit a separate `test_failed` event. Catch `OSError`/`FileNotFoundError` reading the log → build
  a FAIL `result` with `str(e)` in `desc` and log it through the same `test_result` path.
- `int()` over a regex-matched `[0-9]+` cannot raise — no guard needed there.

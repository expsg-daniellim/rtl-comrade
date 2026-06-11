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
`a69d962`). This module appends to `modules/rtl_test/sim.py`, shared with the sim-cycle modules
(`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`, index
[09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

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
        except OSError as e:
            log.error("parse_uvm_read_failed", key=test_run["key"], err=str(e))
            return ("default", { "key": test_run["key"], "result": ... })   # FAIL with str(e)
        counts = parse_uvm_summary(text)   # missing summary → FAIL
        result = uvm_verdict(counts, uvm.max_warns, uvm.max_errors)
        if not result.is_pass():
            log.error("test_failed", key=test_run["key"], log=str(test_run["log"]))
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
4. Emit `("default", {"key": test_run["key"], "result": TestResults(...)})`; on a non-pass
   result `log.error("test_failed", ...)` with the counts and log path; PASS does not log.
5. **Failure — unreadable log.** Wrap step 1's read in `try/except OSError` →
   `log.error("parse_uvm_read_failed", ...)` and emit a FAIL result carrying `str(e)` as `desc`.

## Deliverables

In `modules/rtl_test/sim.py` (continuing from spec 08):

- `ParseUvmLogMod` — reimplements rtl_buddy `UvmVlogPost.get_results()` only: extract the
  UVM Report Summary "Report counts by severity" block; PASS iff `WARNING <=
  ctx["test"].uvm.max_warns and ERROR <= ctx["test"].uvm.max_errors and FATAL == 0`,
  else FAIL with the counts summary in `desc`. Both thresholds are `int` per spec
  [01b — `UVMConfig`](01b-suite-schema.md); their non-negative invariant is enforced
  at YAML deserialisation, so this module does not re-validate. Emits `{"key":
  ctx["key"], "result": TestResults(...)}`.
  **Failure handling**: FAIL result → `log.error` at emission carrying the severity counts
  and `test_run["log"]` path; PASS does not log. `FileNotFoundError`/`OSError` reading
  `test_run["log"]` → emit FAIL with the exception string as `desc` and call `log.error`.
  Missing Report Summary block is already handled (FAIL with explicit message); `int()` on
  regex-matched `[0-9]+` cannot raise `ValueError`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:58-81` — `UvmVlogPost.get_results`; thresholds from `UVMConfig` (`config/uvm.py:3-19`).

**Manifest** — append to the `- file: rtl_test/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: parse-uvm-log, class_name: ParseUvmLogMod }
```

## Tests

In `modules/tests/test_post.py`:

- `parse-uvm-log` against fixture logs: zero severities → PASS; over-threshold → FAIL;
  no-summary → FAIL "Invalid UVM Report Summary".

## Acceptance criteria

- Tests pass.
- `ParseUvmLogMod`: fixture-by-fixture comparison against rtl_buddy `UvmVlogPost` on the
  same log files produces identical `TestResults`.

## Constraints

- Verdict: PASS **iff** `WARNING <= max_warns and ERROR <= max_errors and FATAL == 0`; else FAIL
  with the counts summary in `desc`.
- A missing Report Summary block is itself a FAIL (`"Invalid UVM Report Summary"`).
- Do **not** re-validate the thresholds — their non-negative invariant is enforced at YAML
  deserialisation (spec [01b](01b-suite-schema.md)).
- A FAIL verdict → `log.error("test_failed", …)` at emission; PASS does not log. Catch
  `OSError`/`FileNotFoundError` reading the log → FAIL with `str(e)` in `desc` and `log.error`.
- `int()` over a regex-matched `[0-9]+` cannot raise — no guard needed there.

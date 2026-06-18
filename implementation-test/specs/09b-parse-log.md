# Spec 09b: parse-log (`ParseLogMod`)

**Depends on:** spec 01 (schema).
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

Re-implement rtl_buddy's `VlogPost.get_results()` (with three corrections) to classify a
plain sim log into PASS/FAIL/NA.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   test_run
outputs:  default → result
```

```python
class ParseLogMod:
    def run(self, test_run):
        try:
            text = Path(test_run["log"]).read_text()
            result = scan_pass_fail(text)            # FAIL wins; PASS; else NA
        except OSError as e:
            result = make_fail_result(desc=str(e))   # unreadable log → FAIL
        log_fn = log.error if not result.is_pass() else log.info   # ERROR drives exit on non-pass
        log_fn("test_result", key=test_run["key"], test_name=test_run["test"].get_name(),
               result=result.results["result"], desc=result.results["desc"])
        return ("default", { "key": test_run["key"], "result": result })
```

## Algorithm

1. Read the log: `text = Path(test_run["log"]).read_text()`.
2. Scan line-by-line, recording the first match of each: `re.match(r"PASS\b\s*(.*)", line)`,
   `re.match(r"FAIL\b\s*(.*)", line)`, and `re.match(r"(ERR|FAT):\s*(.*)", line)`. The `\b` word
   boundary is correction #3 — it keeps a line like `PASSTHROUGH ...` from matching PASS.
3. Resolve the verdict (correction #1 — FAIL wins): `if match_fail` → FAIL; `elif match_pass` →
   PASS; else NA (`{"result": "NA", "desc": "test result unknown"}`). Correction #2: when
   `match_fail` is set but `match_err` is not, take `desc = match_fail.group(1)` rather than
   dereferencing the absent `match_err` (no crash).
4. **Log the verdict directly, then emit.** One `test_result` event per verdict:
   `log.error("test_result", key=, result=, desc=)` when `not result.is_pass()` (FAIL **and NA** —
   the ERROR is the deferred-exit driver), else `log.info("test_result", ...)` (PASS) — the same
   pattern `early-stop-gate` (`10a`) uses. Then return `("default", {"key": test_run["key"],
   "result": result})`. `SummaryProcessor` watches `test_result` and renders the row; the
   `default` port stays unwired.
5. **Failure — unreadable log.** Wrap step 1 in `try/except OSError` (incl. `FileNotFoundError`)
   → build a FAIL `result` carrying `str(e)` as `desc` and fall through to step 4 (logged as a
   non-pass `test_result`, so it drives the exit) — a read failure goes through the same
   `test_result` path, not a distinct event.

## Deliverables

In `modules/rtl_buddy/sim.py` (continuing from spec 08):

- `ParseLogMod` — re-implements rtl_buddy `VlogPost.get_results()` with three corrections
  ([07 settled 15](../07-ambiguities-and-assumptions.md)): scan `test_run["log"]` line-by-line,
  recording the first match of `re.match(r"PASS\b\s*(.*)", line)`,
  `re.match(r"FAIL\b\s*(.*)", line)`, and `re.match(r"(ERR|FAT):\s*(.*)", line)`, then
  resolve with `if match_fail / elif match_pass / else NA` — FAIL wins; if `match_fail` is
  set but `match_err` is not, `desc = match_fail.group(1)` (no crash). Default `{"result":
  "NA", "desc": "test result unknown"}`. Emits `{"key": ctx["key"], "result":
  TestResults(...)}`.
  **Failure handling**: every verdict is logged once as `test_result` — `log.error` when
  `not result.is_pass()` (FAIL **and NA**; the ERROR is the exit driver), `log.info` when PASS
  (carrying `key`/`result`/`desc`). `FileNotFoundError`/`OSError` opening `test_run["log"]` →
  build a FAIL `result` with the exception string as `desc` and log it through the same
  `test_result` path — not a distinct event.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:23-45` — `VlogPost.get_results` (corrected per [07 settled 15](../07-ambiguities-and-assumptions.md)).

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: parse-log, class_name: ParseLogMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `tmp_path` fixture log files (one per case); a
`test_run` dict whose `log` points at them; `logging_handler` to assert one `test_result` event
per verdict (ERROR on non-pass, INFO on PASS). Compare against rtl_buddy `VlogPost` on the parity
cases.

- Log with a `PASS …` line and no FAIL → emits `("default", {result: PASS})` and one
  `log.info("test_result", result="PASS", …)`; `logging_handler.failure is False` (PASS does not
  drive the exit).
- Log with a `FAIL …` line and an `ERR: …` line → emits `("default", {result: FAIL})` with
  `desc` from the ERR group and one `log.error("test_result", result="FAIL", …)`;
  `logging_handler.failure is True` (rtl_buddy parity).
- Log with both `FAIL` and `PASS` lines → emits FAIL (correction #1: FAIL wins over PASS).
- Log with a `FAIL` line but no `ERR:`/`FAT:` → emits FAIL with `desc = match_fail.group(1)`,
  no crash (correction #2: absent `match_err` is not dereferenced).
- Log whose only candidate is `PASSTHROUGH …` → emits NA and `log.error("test_result",
  result="NA", …)`, `logging_handler.failure is True` (correction #3: `\b` word boundary, so
  `PASSTHROUGH` is not `PASS`; **and** NA is non-pass, so it drives the exit — see R2).
- Log with no PASS/FAIL/ERR lines → emits NA with `desc = "test result unknown"` and
  `log.error("test_result", …)`, `failure is True`.
- `test_run["log"]` points at a missing file → `FileNotFoundError`/`OSError` caught → emits
  FAIL with `str(e)` in `desc`, logged as an ERROR `test_result` (boundary: unreadable log routes
  to a non-pass `test_result`, driving the exit).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: emits a `result` whose verdict is identical to rtl_buddy
  `VlogPost` on clean-PASS, clean-FAIL-with-ERR, and NA fixtures; intentionally diverges on
  FAIL+PASS, FAIL-without-ERR, and word-boundary cases — see
  [07 settled 15](../07-ambiguities-and-assumptions.md). Every verdict is logged once as
  `test_result` — ERROR on FAIL/NA (the exit driver), INFO on PASS — which `SummaryProcessor`
  collects ([10c](10c-summary-handler.md)).
- Failure idiom exercised: an unreadable log → a FAIL `result` carrying `str(e)` in `desc`,
  logged as an ERROR `test_result`.
- The `modules/config.yaml` manifest entry `{ name: parse-log, class_name: ParseLogMod }`
  validates and the harness resolves `parse-log` → `ParseLogMod`.

## Constraints

- Apply the three corrections exactly: FAIL wins over PASS; use the `\b` word boundary
  (`PASS\b`/`FAIL\b`) so `PASSTHROUGH…` does not match; when `match_fail` is set but `match_err`
  is not, `desc = match_fail.group(1)` (do **not** dereference the absent `match_err`).
- Default verdict is NA with `desc = "test result unknown"`.
- Log every verdict once as `test_result`: `log.error("test_result", key, result, desc)` when
  `not is_pass()` (FAIL **and NA** — the deferred-exit driver), else `log.info("test_result", …)`
  (PASS). Every verdict goes through the one `test_result` path — do **not** add a distinct event.
- Catch `OSError`/`FileNotFoundError` opening `test_run["log"]` → build a FAIL `result` carrying
  `str(e)` as `desc` and log it through the same `test_result` path. Emit the result on the
  string-literal `default` port.

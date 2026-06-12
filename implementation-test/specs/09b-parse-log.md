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
`a69d962`). This module appends to `modules/rtl_test/sim.py`, which is created by spec
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
        except OSError as e:
            log.error("parse_log_read_failed", key=test_run["key"], err=str(e))
            return ("default", { "key": test_run["key"], "result": ... })   # FAIL with str(e)
        result = scan_pass_fail(text)   # FAIL wins; PASS; else NA
        if not result.is_pass():
            log.error("test_failed", key=test_run["key"], log=str(test_run["log"]))
        return ("default", { "key": test_run["key"], "result": result })
```

## Algorithm

1. Read the log: `text = Path(test_run["log"]).read_text()`.
2. Scan line-by-line, recording the first match of each: `re.match(r"PASS\b\s*(.*)", line)`,
   `re.match(r"FAIL\b\s*(.*)", line)`, and `re.match(r"(ERR|FAT):\s*(.*)", line)`. The `\b` word
   boundary is correction #3 — a line like `PASSTHROUGH ...` no longer matches PASS.
3. Resolve the verdict (correction #1 — FAIL wins): `if match_fail` → FAIL; `elif match_pass` →
   PASS; else NA (`{"result": "NA", "desc": "test result unknown"}`). Correction #2: when
   `match_fail` is set but `match_err` is not, take `desc = match_fail.group(1)` rather than
   dereferencing the absent `match_err` (no crash).
4. Emit `("default", {"key": test_run["key"], "result": TestResults(...)})`. On a non-pass
   result, `log.error("test_failed", ...)` at emission with the matched FAIL line and the log
   path; PASS/NA does not log.
5. **Failure — unreadable log.** Wrap step 1 in `try/except OSError` (incl. `FileNotFoundError`)
   → `log.error("parse_log_read_failed", ...)` and emit a FAIL result carrying `str(e)` as
   `desc`.

## Deliverables

In `modules/rtl_test/sim.py` (continuing from spec 08):

- `ParseLogMod` — re-implements rtl_buddy `VlogPost.get_results()` with three corrections
  ([07 settled 15](../07-ambiguities-and-assumptions.md)): scan `test_run["log"]` line-by-line,
  recording the first match of `re.match(r"PASS\b\s*(.*)", line)`,
  `re.match(r"FAIL\b\s*(.*)", line)`, and `re.match(r"(ERR|FAT):\s*(.*)", line)`, then
  resolve with `if match_fail / elif match_pass / else NA` — FAIL wins; if `match_fail` is
  set but `match_err` is not, `desc = match_fail.group(1)` (no crash). Default `{"result":
  "NA", "desc": "test result unknown"}`. Emits `{"key": ctx["key"], "result":
  TestResults(...)}`.
  **Failure handling**: FAIL result → `log.error` at emission carrying the matched FAIL
  line and `test_run["log"]` path; PASS/NA does not log. `FileNotFoundError`/`OSError` opening
  `test_run["log"]` → emit FAIL with the exception string as `desc` and call `log.error`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:23-45` — `VlogPost.get_results` (corrected per [07 settled 15](../07-ambiguities-and-assumptions.md)).

**Manifest** — append to the `- file: rtl_test/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: parse-log, class_name: ParseLogMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `tmp_path` fixture log files (one per case); a
`test_run` dict whose `log` points at them; `logging_handler` to assert `test_failed` ERROR
on the non-pass verdicts. Compare against rtl_buddy `VlogPost` on the parity cases.

- Log with a `PASS …` line and no FAIL → emits `("default", {result: PASS})`, no log (rtl_buddy
  parity).
- Log with a `FAIL …` line and an `ERR: …` line → emits `("default", {result: FAIL})` with
  `desc` from the ERR group; `logging_handler.failure is True` (rtl_buddy parity).
- Log with both `FAIL` and `PASS` lines → emits FAIL (correction #1: FAIL wins over PASS).
- Log with a `FAIL` line but no `ERR:`/`FAT:` → emits FAIL with `desc = match_fail.group(1)`,
  no crash (correction #2: absent `match_err` is not dereferenced).
- Log whose only candidate is `PASSTHROUGH …` → emits NA, no log (correction #3: `\b` word
  boundary, `PASSTHROUGH` is not `PASS`).
- Log with no PASS/FAIL/ERR lines → emits NA with `desc = "test result unknown"`, no log.
- `test_run["log"]` points at a missing file → `FileNotFoundError`/`OSError` caught → emits
  FAIL with `str(e)` in `desc`, `log.error` (boundary: unreadable log routes to FAIL).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: emits a `result` whose verdict is identical to rtl_buddy
  `VlogPost` on clean-PASS, clean-FAIL-with-ERR, and NA fixtures; intentionally diverges on
  FAIL+PASS, FAIL-without-ERR, and word-boundary cases — see
  [07 settled 15](../07-ambiguities-and-assumptions.md). A FAIL result logs at ERROR; PASS/NA
  does not log.
- Failure idiom exercised: an unreadable log → `log.error("parse_log_read_failed", ...)` and
  a FAIL `result` carrying `str(e)` in `desc`.
- The `modules/config.yaml` manifest entry `{ name: parse-log, class_name: ParseLogMod }`
  validates and the harness resolves `parse-log` → `ParseLogMod`.

## Constraints

- Apply the three corrections exactly: FAIL wins over PASS; use the `\b` word boundary
  (`PASS\b`/`FAIL\b`) so `PASSTHROUGH…` does not match; when `match_fail` is set but `match_err`
  is not, `desc = match_fail.group(1)` (do **not** dereference the absent `match_err`).
- Default verdict is NA with `desc = "test result unknown"`.
- A FAIL verdict → `log.error("test_failed", …)` at emission (the deferred-exit driver); PASS
  and NA do **not** log.
- Catch `OSError`/`FileNotFoundError` opening `test_run["log"]` → emit a FAIL `result` carrying
  `str(e)` as `desc` and `log.error`. Emit on the string-literal `default` port.

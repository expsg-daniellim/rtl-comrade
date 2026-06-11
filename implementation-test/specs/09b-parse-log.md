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
`a69d962`). This module appends to `modules/rtl_test/sim.py`, shared with the sim-cycle modules
(`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`, index
[09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

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

In `modules/tests/test_post.py`:

- `parse-log` against fixture logs: clean PASS; clean FAIL with `ERR:`; FAIL+PASS → FAIL
  (corrected, FAIL wins); FAIL without `ERR:` → FAIL with `desc = fail_line` (no crash);
  `PASSTHROUGH ...` line → NA (word-boundary fix); result-unknown NA;
  `FileNotFoundError` on `test_run["log"]` → FAIL.

## Acceptance criteria

- Tests pass.
- `ParseLogMod`: identical to rtl_buddy `VlogPost` on clean-PASS, clean-FAIL-with-ERR,
  and NA fixtures; intentionally diverges on FAIL+PASS, FAIL-without-ERR, and
  word-boundary cases — see [07 settled 15](../07-ambiguities-and-assumptions.md).

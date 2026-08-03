# Spec 09b: parse-log (`ParseLogMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Post-processing section](../03-module-catalog.md), [07 settled 14, 15](../07-ambiguities-and-assumptions.md). Parent index: [idx-09 — Post-processing modules](../idx-09-post.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Re-implement rtl_buddy's `VlogPost.get_results()` (with three corrections) to classify a plain sim log into PASS/FAIL/NA.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          test, proc   (joined by key — plain branch of route-post)
outputs:         default → TestResult (self-keyed)
```

`scan_pass_fail` below is an **illustrative stand-in** for the inline scan/verdict in Algorithm steps 2–3 — implement that logic in the module, do not import it. The only imported symbol here is `TestResult` (spec [01](01-shared-schema.md)); every verdict (and the unreadable-log FAIL) is built via its `TestResult.parse(...)` `@classmethod` (`type_=PARSE`). rtl_buddy's `VlogPost` is the reimplementation reference and parity oracle, **not** an import — see the [specs README preamble](README.md).

```python
class ParseLogMod:
    def run(self, test:TestConfig, proc:Proc):
        try:
            text = Path(proc.stdout_path).read_text()       # log = proc's echoed stdout_path
            verdict, desc = scan_pass_fail(text)            # stand-in: inline scan/verdict (steps 2-3); FAIL wins; PASS; else NA
            result = TestResult.parse(test.key, test.get_name(), verdict, desc)  # self-keyed PARSE result
            event = {"FAIL": "parse_log_failed", "NA": "parse_log_unknown"}.get(verdict)   # only a non-pass verdict gets an event
        except OSError as e:
            result = TestResult.parse(test.key, test.get_name(), "FAIL", str(e))   # unreadable log → FAIL (still a PARSE-originated result)
            event = "parse_log_unreadable"                  # distinct fail case, its own event name
        if event is not None:                               # only a non-pass verdict logs (the deferred-exit driver)
            log.error(event, key=test.key, test_name=test.get_name(), path=str(proc.stdout_path), desc=result.desc)   # diagnostic fields
        return ("default", result)                          # TestResult → results-summary
```

## Algorithm

1. Read the log: `text = Path(proc.stdout_path).read_text()` (`proc` echoes the redirect paths, so the log is `proc.stdout_path`).
2. Scan line-by-line, recording the first match of each: `re.match(r"PASS\b\s*(.*)", line)`, `re.match(r"FAIL\b\s*(.*)", line)`, and `re.match(r"(ERR|FAT):\s*(.*)", line)`. The `\b` word boundary is correction #3 — it keeps a line like `PASSTHROUGH ...` from matching PASS.
3. Resolve the verdict (correction #1 — FAIL wins): `if match_fail` → FAIL; `elif match_pass` → PASS; else NA (`{"result": "NA", "desc": "test result unknown"}`). Correction #2: when `match_fail` is set but `match_err` is not, take `desc = match_fail.group(1)` rather than dereferencing the absent `match_err` (no crash).
4. **Log a non-pass verdict, then emit.** A FAIL/NA logs its per-case event with `log.error` — `parse_log_failed` (FAIL), `parse_log_unknown` (NA) — the deferred-exit driver. Then return `("default", result)` (the self-keyed `TestResult.parse`). The emitted `TestResult` → `results-summary` ([10d](10d-summarise-results.md)) for every verdict; the `default` port is wired to it.
5. **Failure — unreadable log.** Wrap step 1 in `try/except OSError` (incl. `FileNotFoundError`) → build a FAIL `result` carrying `str(e)` as `desc`, and log it under its own event `parse_log_unreadable` at `log.error` (it drives the exit). A read failure is a distinct fail case with its own event name, not folded into the verdict events.

## Deliverables

In `modules/rtl_buddy/sim.py` (continuing from spec 08):

- `ParseLogMod` — `(test, proc)`, `keyed_join`; re-implements rtl_buddy `VlogPost.get_results()` with three corrections ([07 settled 15](../07-ambiguities-and-assumptions.md)): scan `proc.stdout_path` line-by-line, recording the first match of `re.match(r"PASS\b\s*(.*)", line)`, `re.match(r"FAIL\b\s*(.*)", line)`, and `re.match(r"(ERR|FAT):\s*(.*)", line)`, then resolve with `if match_fail / elif match_pass / else NA` — FAIL wins; if `match_fail` is set but `match_err` is not, `desc = match_fail.group(1)` (no crash). Default verdict `("NA", "test result unknown")`. Builds each verdict via `TestResult.parse(test.key, test.get_name(), verdict, desc)` (`type_=PARSE`) and emits it directly on `default` (self-keyed; no `Result` wrapper).
  **Failure handling**: a non-pass verdict logs its per-case event — `parse_log_failed` (FAIL), `parse_log_unknown` (NA), each `log.error` (the exit driver, logging `key`/`test_name`/`path`/`desc` — no `result` kwarg). `FileNotFoundError`/`OSError` opening `proc.stdout_path` → build a FAIL `result` with the exception string as `desc` and log it under its own `parse_log_unreadable` (`log.error`) — a distinct fail case. No event uses the generic `test_result`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:23-45` — `VlogPost.get_results` (corrected per [07 settled 15](../07-ambiguities-and-assumptions.md)).

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: parse-log, class_name: ParseLogMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `tmp_path` fixture log files (one per case); `test` (`{key, value}`) and `proc` (`{key, stdout_path, …}`, `stdout_path` pointing at them) dict fixtures; `logging_handler` to assert the non-pass verdicts log their per-case event (`parse_log_failed`/`parse_log_unknown`/`parse_log_unreadable`, all ERROR) and a PASS keeps `failure` `False`. Drive `run(test, proc)` directly. Compare against rtl_buddy `VlogPost` on the parity cases.

- Log with a `PASS …` line and no FAIL → emits `("default", {result: PASS})`; `logging_handler.failure is False` (PASS does not drive the exit).
- Log with a `FAIL …` line and an `ERR: …` line → emits `("default", {result: FAIL})` with `desc` from the ERR group and one `log.error("parse_log_failed", path=…, desc=…)` (no `result` kwarg); `logging_handler.failure is True` (rtl_buddy parity).
- Log with both `FAIL` and `PASS` lines → emits FAIL (correction #1: FAIL wins over PASS).
- Log with a `FAIL` line but no `ERR:`/`FAT:` → emits FAIL with `desc = match_fail.group(1)`, no crash (correction #2: absent `match_err` is not dereferenced).
- Log whose only candidate is `PASSTHROUGH …` → emits NA and `log.error("parse_log_unknown", path=…, desc=…)`, `logging_handler.failure is True` (correction #3: `\b` word boundary, so `PASSTHROUGH` is not `PASS`; **and** NA is non-pass, so it drives the exit).
- Log with no PASS/FAIL/ERR lines → emits NA with `desc = "test result unknown"` and `log.error("parse_log_unknown", …)`, `failure is True`.
- `proc.stdout_path` points at a missing file → `FileNotFoundError`/`OSError` caught → emits FAIL with `str(e)` in `desc`, logged as an ERROR `parse_log_unreadable` (boundary: unreadable log is a distinct fail case, driving the exit).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: emits a `result` whose verdict is identical to rtl_buddy `VlogPost` on clean-PASS, clean-FAIL-with-ERR, and NA fixtures; intentionally diverges on FAIL+PASS, FAIL-without-ERR, and word-boundary cases — see [07 settled 15](../07-ambiguities-and-assumptions.md). Only a non-pass verdict logs (`parse_log_failed`/`parse_log_unknown`, ERROR — the exit driver). The emitted `TestResult` → `results-summary` ([10d](10d-summarise-results.md)) for every verdict.
- Failure idiom exercised: an unreadable log → a FAIL `result` carrying `str(e)` in `desc`, logged as an ERROR `parse_log_unreadable`.
- The `modules/config.yaml` manifest entry `{ name: parse-log, class_name: ParseLogMod }` validates and the harness resolves `parse-log` → `ParseLogMod`.

## Constraints

- Apply the three corrections exactly: FAIL wins over PASS; use the `\b` word boundary (`PASS\b`/`FAIL\b`) so `PASSTHROUGH…` does not match; when `match_fail` is set but `match_err` is not, `desc = match_fail.group(1)` (do **not** dereference the absent `match_err`).
- Default verdict is NA with `desc = "test result unknown"`.
- Log a non-pass verdict under its per-case event name (`parse_log_failed`/`parse_log_unknown`), `log.error` when `not is_pass()` (FAIL **and NA** — the deferred-exit driver). Do **not** use the generic `test_result` event.
- `keyed_join` over `test`+`proc` (key_field `key`). Catch `OSError`/`FileNotFoundError` opening `proc.stdout_path` → build a FAIL `result` via `TestResult.parse(test.key, test.get_name(), "FAIL", str(e))` and log it under `parse_log_unreadable` (`log.error`). Emit the self-keyed `TestResult` on the string-literal `default` port (→ `results-summary`).

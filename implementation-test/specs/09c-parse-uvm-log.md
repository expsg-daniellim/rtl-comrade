# Spec 09c: parse-uvm-log (`ParseUvmLogMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`ParseUvmLogMod` reads `test.uvm.max_warns` / `.max_errors` — `UVMConfig` lives in 01b).
**References:** [03 — Post-processing section](../03-module-catalog.md), [07 settled 14, 15](../07-ambiguities-and-assumptions.md). Parent index: [idx-09 — Post-processing modules](../idx-09-post.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Reimplement rtl_buddy's `UvmVlogPost.get_results()` to classify a UVM sim log from its Report Summary severity counts.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:        keyed_join
contract_config: key_field: key
inputs:          test, proc   (joined by key — uvm branch of route-post)
outputs:         default → TestResult (self-keyed)
```

`uvm_classify` below is an **illustrative stand-in** for the inline logic in Algorithm steps 2–3 (Report-Summary parse + verdict, returning the per-case event name) — implement that logic in the module, do not import it (it is not a symbol anyone delivers). The only imported symbol here is `TestResult` (spec [01](01-shared-schema.md)); every verdict (and the unreadable-log FAIL) is built via its `TestResult.parse(...)` `@classmethod` (`type_=PARSE`). rtl_buddy's `UvmVlogPost` is the reimplementation reference and parity oracle, **not** an import — see the [specs README preamble](README.md).

```python
class ParseUvmLogMod:
    def run(self, test:TestConfig, proc:Proc):
        uvm = test.uvm
        try:
            text = Path(proc.stdout_path).read_text()   # log = proc's echoed stdout_path
            verdict, desc, event = uvm_classify(text, uvm.max_warns, uvm.max_errors)  # stand-in (steps 2-3): Report-Summary parse + verdict; event is None on PASS, else the per-case fail event:
                                                        #   parse_uvm_failed (counts) / parse_uvm_no_summary / parse_uvm_invalid_summary
            result = TestResult.parse(test.key, test.get_name(), verdict, desc)   # self-keyed PARSE result
        except OSError as e:
            result = TestResult.parse(test.key, test.get_name(), "FAIL", str(e))   # unreadable log → FAIL (still a PARSE-originated result)
            event = "parse_uvm_unreadable"              # distinct fail case, its own event name
        if event is not None:                           # only a FAIL logs (the exit driver)
            log.error(event, key=test.key, test_name=test.get_name(), path=str(proc.stdout_path), desc=result.desc)   # diagnostic fields
        return ("default", result)                      # TestResult → results-summary
```

## Algorithm

1. Read the thresholds and log: `uvm = test.uvm` (non-negative `max_warns` / `max_errors`, validated at deserialisation — not re-checked here); `text = Path(proc.stdout_path).read_text()` (`proc` echoes the redirect paths).
2. Parse the UVM "Report counts by severity" block into WARNING/ERROR/FATAL counts. Two distinct structural FAILs here, matching rtl_buddy's two messages (`vlog_post.py:67,71`), each with its own event name:
   - the **Report Summary regex does not match at all** (no summary block) → `desc = f"No UVM Report Summary detected. See {path}."`, event `parse_uvm_no_summary`;
   - the block matches but **WARNING/ERROR/FATAL are not all present** in the parsed counts → `desc = f"Invalid UVM Report Summary detected. See {path}"`, event `parse_uvm_invalid_summary`.
3. Verdict: PASS (no event — a PASS is not logged) iff `WARNING <= uvm.max_warns and ERROR <= uvm.max_errors and FATAL == 0`, else FAIL (event `parse_uvm_failed`) with the counts summary in `desc`.
4. **Log a FAIL, then emit.** A FAIL logs its per-case event (`parse_uvm_failed`/`parse_uvm_no_summary`/`parse_uvm_invalid_summary`) with `log.error` (the exit driver). Then return `("default", result)` (the self-keyed `TestResult.parse`). The emitted `TestResult` → `results-summary` ([10d](10d-summarise-results.md)) for every verdict; the `default` port is wired to it.
5. **Failure — unreadable log.** Wrap step 1's read in `try/except OSError` → build a FAIL `result` carrying `str(e)` as `desc`, and log it under its own event `parse_uvm_unreadable` at `log.error` (it drives the exit) — a distinct fail case, not folded into the verdict events.

## Deliverables

In `modules/rtl_buddy/sim.py` (continuing from spec 08):

- `ParseUvmLogMod` — `(test, proc)`, `keyed_join`; reimplements rtl_buddy `UvmVlogPost.get_results()` only: extract the UVM Report Summary "Report counts by severity" block; PASS iff `WARNING <= test.uvm.max_warns and ERROR <= test.uvm.max_errors and FATAL == 0`, else FAIL with the counts summary in `desc`. Both thresholds are `int` per spec [01b — `UVMConfig`](01b-suite-schema.md); their non-negative invariant is enforced at YAML deserialisation, so this module does not re-validate. Builds the verdict via `TestResult.parse(test.key, test.get_name(), verdict, desc)` (`type_=PARSE`) and emits it directly on `default` (self-keyed; no `Result` wrapper).
  **Failure handling**: a FAIL logs its per-case event — `parse_uvm_failed` (counts FAIL), `parse_uvm_no_summary` (no summary block), `parse_uvm_invalid_summary` (incomplete block), all `log.error` (the exit drivers; each logging `key`/`test_name`/`path`/`desc` — no `result` kwarg). `FileNotFoundError`/`OSError` reading `proc.stdout_path` → build a FAIL `result` with the exception string as `desc` and log it under its own `parse_uvm_unreadable` (`log.error`) — a distinct fail case. No event uses the generic `test_result`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:58-81` — `UvmVlogPost.get_results`; thresholds from `UVMConfig` (`config/uvm.py:3-19`).

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: parse-uvm-log, class_name: ParseUvmLogMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `tmp_path` UVM log fixtures (varying Report Summary counts; one without a summary block); a `test` edge (`{key, value}`, value with `.uvm` carrying `max_warns`/`max_errors`) and a `proc` edge (`{key, stdout_path}` pointing at the log); `logging_handler` for the FAIL paths. Drive `run(test, proc)` directly. Compare fixture-by-fixture against rtl_buddy `UvmVlogPost`.

- Report Summary with `WARNING=0, ERROR=0, FATAL=0` within thresholds → emits `("default", {result: PASS})`; `failure is False` (PASS does not drive the exit).
- `WARNING == max_warns` and `ERROR == max_errors`, `FATAL=0` → emits PASS (boundary: inclusive `<=` edge).
- `ERROR > max_errors` (others within bounds) → emits FAIL with the counts summary in `desc` and `log.error("parse_uvm_failed", path=…, desc=…)` (no `result` kwarg); `failure is True`.
- `WARNING > max_warns` → emits FAIL, `log.error("parse_uvm_failed", …)`.
- `FATAL == 1` with WARNING/ERROR within thresholds → emits FAIL (boundary: `FATAL == 0` is absolute, not threshold-gated).
- Log with **no** Report Summary block (regex no match) → emits FAIL with `desc = "No UVM Report Summary detected. See {path}."`, `log.error("parse_uvm_no_summary", …)`.
- Log **with** a Report Summary block but missing one of WARNING/ERROR/FATAL → emits FAIL with `desc = "Invalid UVM Report Summary detected. See {path}"`, `log.error("parse_uvm_invalid_summary", …)` (boundary: the two distinct rtl_buddy messages are not conflated — distinct event names too).
- `proc.stdout_path` missing → `OSError` caught → emits FAIL with `str(e)` in `desc`, logged as an ERROR `parse_uvm_unreadable`.

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: a fixture-by-fixture comparison against rtl_buddy `UvmVlogPost` on the same log files produces identical `TestResult`.
- Failure idioms exercised: a log with no UVM summary → a FAIL `result`; a missing `proc.stdout_path` → `OSError` caught → FAIL with `str(e)` in `desc`. A FAIL logs its per-case event (`parse_uvm_failed`/`parse_uvm_no_summary`/`parse_uvm_invalid_summary`/`parse_uvm_unreadable`, all ERROR — the exit driver). The emitted `TestResult` → `results-summary` ([10d](10d-summarise-results.md)) for every verdict.
- The `modules/config.yaml` manifest entry `{ name: parse-uvm-log, class_name: ParseUvmLogMod }` validates and the harness resolves `parse-uvm-log` → `ParseUvmLogMod`.

## Constraints

- Verdict: PASS **iff** `WARNING <= max_warns and ERROR <= max_errors and FATAL == 0`; else FAIL with the counts summary in `desc`.
- A missing Report Summary block is a FAIL with `"No UVM Report Summary detected. See {path}."`; a block present but missing a severity count is a FAIL with `"Invalid UVM Report Summary detected. See {path}"` — keep both rtl_buddy messages distinct (`vlog_post.py:67,71`), do not conflate them (the fixture-by-fixture parity check compares `desc`).
- Do **not** re-validate the thresholds — their non-negative invariant is enforced at YAML deserialisation (spec [01b](01b-suite-schema.md)).
- Log a FAIL under its per-case event name (`parse_uvm_failed`/`parse_uvm_no_summary`/`parse_uvm_invalid_summary`), `log.error` (the exit driver). Do **not** use the generic `test_result` event. Catch `OSError`/`FileNotFoundError` reading the log → build a FAIL `result` with `str(e)` in `desc` and log it under `parse_uvm_unreadable` (`log.error`).
- `int()` over a regex-matched `[0-9]+` cannot raise — no guard needed there.

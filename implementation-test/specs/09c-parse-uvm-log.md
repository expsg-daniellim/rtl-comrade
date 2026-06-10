# Spec 09c: parse-uvm-log (`ParseUvmLogMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`ParseUvmLogMod`
reads `ctx["test"].uvm.max_warns` / `.max_errors` — `UVMConfig` lives in 01b).
**References:** [03 — Post-processing section](../03-module-catalog.md),
[07 settled 14, 15](../07-ambiguities-and-assumptions.md). Parent index:
[09 — Post-processing modules](09-post-modules.md).

## Goal

Reimplement rtl_buddy's `UvmVlogPost.get_results()` to classify a UVM sim log from its
Report Summary severity counts.

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

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_post.py`:

- `parse-uvm-log` against fixture logs: zero severities → PASS; over-threshold → FAIL;
  no-summary → FAIL "Invalid UVM Report Summary".

## Acceptance criteria

- Tests pass.
- `ParseUvmLogMod`: fixture-by-fixture comparison against rtl_buddy `UvmVlogPost` on the
  same log files produces identical `TestResults`.

# Spec 09: Post-processing modules

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RoutePostMod`
reads `ctx["test"].uvm`; `ParseUvmLogMod` reads `ctx["test"].uvm.max_warns` /
`.max_errors` — `UVMConfig` lives in 01b).
**References:** [03 — Post-processing section](../03-module-catalog.md), [07 settled 14, 15](../07-ambiguities-and-assumptions.md).

## Goal

Implement the log-parse trio: a uvm/plain classifier router and two atomic parsers.

## Deliverables

In `modules/rtl_test/sim.py` (continuing from spec 08):

- `RoutePostMod` — `(ctx)` → `("uvm", ctx)` if `ctx["test"].uvm is not None` else
  `("plain", ctx)`. `ctx["test"].uvm` is `UVMConfig | None` per spec
  [01b](01b-suite-schema.md). Pure data classifier; no scheduling.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:293-298` — the `if self.test_cfg.uvm:` dispatch in `VlogSim.post`.
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

Tests in `modules/tests/test_post.py`:
- `route-post` routes correctly on `uvm` presence/absence.
- `parse-log` against fixture logs: clean PASS; clean FAIL with `ERR:`; FAIL+PASS → FAIL
  (corrected, FAIL wins); FAIL without `ERR:` → FAIL with `desc = fail_line` (no crash);
  `PASSTHROUGH ...` line → NA (word-boundary fix); result-unknown NA;
  `FileNotFoundError` on `test_run["log"]` → FAIL.
- `parse-uvm-log` against fixture logs: zero severities → PASS; over-threshold → FAIL;
  no-summary → FAIL "Invalid UVM Report Summary".

## Acceptance criteria

- Tests pass.
- `ParseUvmLogMod`: fixture-by-fixture comparison against rtl_buddy `UvmVlogPost` on the
  same log files produces identical `TestResults`.
- `ParseLogMod`: identical to rtl_buddy `VlogPost` on clean-PASS, clean-FAIL-with-ERR,
  and NA fixtures; intentionally diverges on FAIL+PASS, FAIL-without-ERR, and
  word-boundary cases — see [07 settled 15](../07-ambiguities-and-assumptions.md).

## Notes

`route-post` + two-parsers is the example I keep returning to for "atomic-by-function,
not by signature" — make sure the implementation preserves that split rather than
collapsing them back into one node.

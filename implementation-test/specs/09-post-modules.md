# Spec 09: Post-processing modules

**Depends on:** spec 01 (schema).
**References:** [03 — Post-processing section](../03-module-catalog.md), [07 settled 14 / open 15](../07-ambiguities-and-assumptions.md).

## Goal

Implement the log-parse trio: a uvm/plain classifier router and two atomic parsers.

## Deliverables

In `modules/rtl_test/sim.py` (continuing from spec 08):

- `RoutePostMod` — `(ctx)` → `("uvm", ctx)` if `ctx["test"].uvm is not None` else
  `("plain", ctx)`. Pure data classifier; no scheduling.
- `ParseLogMod` — reimplements rtl_buddy `VlogPost.get_results()` only: scan `ctx["log"]`
  for `^PASS\s*(.*)`, `^FAIL\s*(.*)`, `^(ERR|FAT):\s*(.*)`; default `{"result": "NA",
  "desc": "test result unknown"}`. Emits `{"key": ctx["key"], "result": TestResults(...)}`.
- `ParseUvmLogMod` — reimplements rtl_buddy `UvmVlogPost.get_results()` only: extract the
  UVM Report Summary "Report counts by severity" block; PASS iff `WARNING <=
  ctx["test"].uvm.max_warns and ERROR <= max_errors and FATAL == 0`, else FAIL with the
  counts summary in `desc`. Emits `{"key": ctx["key"], "result": TestResults(...)}`.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_post.py`:
- `route-post` routes correctly on `uvm` presence/absence.
- `parse-log` against fixture logs: clean PASS, clean FAIL with ERR, FAIL+PASS (PASS
  wins per rtl_buddy quirk), result-unknown NA.
- `parse-uvm-log` against fixture logs: zero severities → PASS; over-threshold → FAIL;
  no-summary → FAIL "Invalid UVM Report Summary".

## Acceptance criteria

- Tests pass.
- Fixture-by-fixture comparison against rtl_buddy's `VlogPost`/`UvmVlogPost` on the same
  log files produces identical `TestResults`.

## Notes

**Open question** ([07 open 15](../07-ambiguities-and-assumptions.md)): rtl_buddy's
`VlogPost` has two quirks worth deciding before merge — PASS wins over FAIL when both
appear, and a FAIL line with no matching ERR/FAT line raises `AttributeError`. Faithful
copy inherits both. The default here is to copy faithfully; flag tests and surface the
question if the implementer prefers to fix while porting.

`route-post` + two-parsers is the example I keep returning to for "atomic-by-function,
not by signature" — make sure the implementation preserves that split rather than
collapsing them back into one node.

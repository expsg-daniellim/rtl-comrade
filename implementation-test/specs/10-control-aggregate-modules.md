# Spec 10: Control module, git-status, and the summary logging plugin (index)

**Depends on:** spec 01 (schema). No dependency on spec 02 any more — the `fan-in-results`
relay was removed by TODO #15.
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`.

## Goal

Implement the cross-cutting early-stop gate (reused at three boundaries), the `git-status`
setup node, and the per-graph **logging plugin** that renders the summary table and drives
exit semantics — replacing the removed `aggregate-results` sink (TODO #15).

This spec is split into one ticket per deliverable — build them as independent units.

| Ticket | Deliverable | File | What it does |
|---|---|---|---|
| [10a](10a-early-stop-gate.md) | `EarlyStopGateMod` | `modules/rtl_test/control.py` | Cross-cutting early-stop gate (3 instances). |
| [10b](10b-git-status.md) | `GitStatusMod` | `modules/rtl_test/setup.py` | Record git state as a structured log event. |
| [10c](10c-summary-handler.md) | `SummaryProcessor` | `graphs/log/summary.py` | Accumulate `test_result` rows (results only) and render the summary table. |

**Manifest** — each child ticket carries its exact `modules/config.yaml` line: `EarlyStopGateMod`
opens the `rtl_test/control.py` block ([`10a`](10a-early-stop-gate.md)); `GitStatusMod` appends to
the `rtl_test/setup.py` block ([`10b`](10b-git-status.md)). `graphs/log/summary.py` (the
`SummaryProcessor`, [`10c`](10c-summary-handler.md)) is referenced by `path`/`name` in the
`logging` block, **not** a manifest.

## Acceptance criteria

- Each child ticket's tests pass.
- Exit-code semantics: a run with any FAIL/NA emits ≥1 `log.error` → harness exit 1; an
  all-PASS/SKIP run emits none → exit 0. This reproduces rtl_buddy's
  `exit_code |= 0 if is_pass() else 1` via the per-emission `log.error`, not an aggregator.
- The summary table content matches what `aggregate-results.finalise()` previously produced
  (same `key`/`result`/`desc` columns). The table is **results only** — git state is logged
  separately by `git-status` and falls through to the console, not into the table.
- No `fan-in`/`agg` node exists in `graphs/test.yaml`, and there is **no** separate
  `drop_summary_events` entry; the `logging` block resolves `graphs/log/summary.py` to the
  single `SummaryProcessor` and renders on a normal and a deferred-`ERROR` run (not on CRITICAL).
- `early-stop-gate` exercises both `go`/`stop` ports and `git-status` emits its
  `git_state`/`git_state_unavailable` events; both resolve from `modules/config.yaml` to
  `EarlyStopGateMod` / `GitStatusMod`, and the `logging` block resolves `SummaryProcessor`
  (see [11](11-graph-and-manifests.md#acceptance-criteria)).

## Notes

Adding a new terminal-result source means adding one `log.info("test_result", ...)` call at
the new site — no edge, no handler change.

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent in
the schema package from spec 01) rather than ad-hoc string compares.

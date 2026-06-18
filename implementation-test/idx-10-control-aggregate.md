# idx-10 — Control module, git-status, and the summary logging plugin (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](03-module-catalog.md),
[05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`.

## Goal

Implement the cross-cutting early-stop gate (reused at three boundaries), the `git-status`
setup node, and the per-graph **logging plugin** that renders the summary table and drives
exit semantics.

This spec is split into one ticket per deliverable — build them as independent units.

| Ticket | Deliverable | File | What it does |
|---|---|---|---|
| [10a](specs/10a-early-stop-gate.md) | `EarlyStopGateMod` | `modules/rtl_buddy/control.py` | Cross-cutting early-stop gate (3 instances). |
| [10b](specs/10b-git-status.md) | `GitStatusMod` | `modules/rtl_buddy/setup.py` | Record git state as a structured log event. |
| [10c](specs/10c-summary-handler.md) | `SummaryProcessor` | `graphs/log/summary.py` | Collect the watch-list outcome events (`test_result` + the failure terminals' events) and render the summary table. |

**Manifest** — each child ticket carries its exact `modules/config.yaml` line: `EarlyStopGateMod`
opens the `rtl_buddy/control.py` block ([`10a`](specs/10a-early-stop-gate.md)); `GitStatusMod` appends to
the `rtl_buddy/setup.py` block ([`10b`](specs/10b-git-status.md)). `graphs/log/summary.py` (the
`SummaryProcessor`, [`10c`](specs/10c-summary-handler.md)) is referenced by `path`/`name` in the
`logging` block, **not** a manifest.

## Acceptance criteria

- Each child ticket's tests pass.
- Run-wide exit-code semantics (per-emission `log.error` → exit 1; all-PASS/SKIP → exit 0;
  the `--early-stop` exit-0 divergence) and the outcomes-only summary-table render live in
  [10c](specs/10c-summary-handler.md)'s acceptance criteria; the cross-cutting behaviour is
  exercised end-to-end in [spec 11](specs/11-graph-and-manifests.md) and
  [spec 12](specs/12-end-to-end.md).
- The `logging` block resolves `graphs/log/summary.py` to the single `SummaryProcessor`, which
  renders on a normal and a deferred-`ERROR` run (not on CRITICAL).
- `early-stop-gate` exercises both `go`/`stop` ports and `git-status` emits its
  `git_state`/`git_state_unavailable` events; both resolve from `modules/config.yaml` to
  `EarlyStopGateMod` / `GitStatusMod`, and the `logging` block resolves `SummaryProcessor`
  (see [11](specs/11-graph-and-manifests.md#acceptance-criteria)).

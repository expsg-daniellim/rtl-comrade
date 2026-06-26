# idx-10 — Control module, git-status, and the results-summary node (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](03-module-catalog.md),
[05 — Re-convergence](05-branching-and-results.md#re-convergence-the-summary-returns-as-a-graph-node),
[07 item 27](07-ambiguities-and-assumptions.md), `docs/logger/implementation.md`,
`docs/harness/logging.md`.

## Goal

Implement the cross-cutting early-stop gate (reused at three boundaries), the `git-status`
setup node, and the in-graph **`results-summary` node** that renders the summary table from the
13 terminal `TestResult` ports fanned in by the `any` contract. (The earlier out-of-graph
`SummaryProcessor` logging plugin is retained but dormant — see [10c](specs/10c-summary-handler.md).)

This spec is split into one ticket per deliverable — build them as independent units.

| Ticket | Deliverable | File | What it does |
|---|---|---|---|
| [10a](specs/10a-early-stop-gate.md) | `EarlyStopGateMod` | `modules/rtl_buddy/control.py` | Cross-cutting early-stop gate (3 instances). |
| [10b](specs/10b-git-status.md) | `GitStatusMod` | `modules/rtl_buddy/setup.py` | Record git state as a structured log event. |
| [10c](specs/10c-summary-handler.md) | `SummaryProcessor` | `graphs/log/summary.py` | **Dormant** (superseded by 10d): out-of-graph summary-collection plugin, kept but unwired. |
| [10d](specs/10d-summarise-results.md) | `SummariseResultsMod` | `modules/rtl_buddy/summarise_results.py` | In-graph summary node: the 13 terminal `TestResult` ports fan in via the `any` contract; renders the table from `finalise()`. |

**Manifest** — each child ticket carries its exact `modules/config.yaml` line: `EarlyStopGateMod`
opens the `rtl_buddy/control.py` block ([`10a`](specs/10a-early-stop-gate.md)); `GitStatusMod` appends to
the `rtl_buddy/setup.py` block ([`10b`](specs/10b-git-status.md)); `SummariseResultsMod` opens the
`rtl_buddy/summarise_results.py` block ([`10d`](specs/10d-summarise-results.md)). `graphs/log/summary.py`
(the dormant `SummaryProcessor`, [`10c`](specs/10c-summary-handler.md)) would be referenced by
`path`/`name` in a `logging` block, **not** a manifest — but it is unwired in `test`.

## Acceptance criteria

- Each child ticket's tests pass.
- Run-wide exit-code semantics (per-emission `log.error` → exit 1; all-PASS/SKIP → exit 0;
  the `--early-stop` exit-0 divergence) live in [05 — Result aggregation and exit code](05-branching-and-results.md#result-aggregation-and-exit-code); the outcomes-only summary-table render lives in [10d](specs/10d-summarise-results.md)'s acceptance criteria; the cross-cutting behaviour is
  exercised end-to-end in [spec 11](specs/11-graph-and-manifests.md) and
  [spec 12](specs/12-end-to-end.md).
- The `results-summary` node renders the table from the 13 terminal `TestResult`s fanned in by the
  `any` contract, on a normal and a deferred-`ERROR` run (no-op on a list-mode / CRITICAL run with
  no results); it drives no exit code.
- `early-stop-gate` exercises both `go`/`stop` ports and `git-status` emits its
  `git_state`/`git_state_unavailable` events; both resolve from `modules/config.yaml` to
  `EarlyStopGateMod` / `GitStatusMod`, and `summarise-results` resolves to `SummariseResultsMod`
  (see [11](specs/11-graph-and-manifests.md#acceptance-criteria)).

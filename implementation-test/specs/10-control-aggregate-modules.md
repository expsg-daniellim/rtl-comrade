# Spec 10: Control and aggregate modules

**Depends on:** spec 01 (schema), spec 02 (merge contract).
**References:** [03 — Control / aggregation section](../03-module-catalog.md), [05](../05-branching-and-results.md).

## Goal

Implement the cross-cutting early-stop gate (reused at three boundaries) and the single
collector/sink that drives the exit code.

## Deliverables

In `modules/rtl_test/control.py`:

- `EarlyStopGateMod` — `(ctx, early_stop:str="post")` with module `Config` containing
  `phase:str` (one of `pre`/`comp`/`sim`). Compares `early_stop` against `phase` using
  the ordering `pre < comp < sim < post`; if stop here → `("stop", {"key", "result":
  EarlyStopResults(f"Stopped early at {phase}")})`; else `("go", ctx)`. Three node
  instances in the graph, differing only in `config.phase`.
  **Failure handling**: routing only; no exception caught, no log call. `("stop", ...)`
  is a normal terminal (not a failure) — distinct from the FAIL emitters in spec 05/06.
  See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
- `AggregateResultsMod` — `run(self, result)` accumulates the delivered `result`
  payload into `self._rows`. The 13 upstream terminal ports live on the **contract** side
  (declared in `MergeContract.Config.fan_in`); the module has only the one `result`
  parameter. `finalise()` prints the summary table (`key`/`test_name`, `result`,
  `desc`), and logs `ERROR` if any row's `result.is_pass()` is false. Paired with the
  `merge` contract from spec 02 (`fan_in: result`).
  **Failure handling**: `finalise()` calls
  `log.error("suite_has_failures", n=len(failed))` once if any accumulated row is not
  `is_pass()` — this is the centralised deferred-exit driver. Per-test emission sites
  also call `log.error` as belt-and-braces (see [05 — Log idioms]). `run()` raises
  nothing; an unexpected payload shape from the `merge` contract should propagate as
  `KeyError` / `TypeError` and surface as harness CRITICAL via the bubbling-SystemExit
  catch.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_control_aggregate.py`:
- Gate routing matches expected ordering across all four `early_stop` values for each of
  the three `phase` configurations.
- Aggregate: feeding N rows through the `merge` contract (each routed to `result`
  regardless of which wired input port carried it) produces a single summary; mix of
  PASS/SKIP/FAIL/NA correctly triggers the ERROR-level log (exit code 1 path).

## Acceptance criteria

- Tests pass.
- Aggregator + merge integration test from spec 02 confirms `fan_in: result` delivery
  from `merge` works end-to-end (every wired input fires under `result`).
- A toy 3-port `merge` test plus aggregator finalise reproduces an OR-accumulated exit
  code matching rtl_buddy's `exit_code |= 0 if is_pass() else 1` semantics.

## Notes

The 13 terminal-result input ports live on the **contract** side, not the module. This
requires the harness change described in spec 02's "Prerequisite" section — adding new
terminal-result sources means extending `MergeContract.Config.fan_in`'s input list and
one edge in [06]; the module signature is not touched.

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent
in the schema package from spec 01) rather than ad-hoc string compares.

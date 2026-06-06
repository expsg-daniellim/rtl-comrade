# Spec 10: Control and aggregate modules

**Depends on:** spec 01 (schema), spec 02 (`any` contract + `fan-in-results` module).
**References:** [03 — Control / aggregation section](../03-module-catalog.md), [05](../05-branching-and-results.md).

## Goal

Implement the cross-cutting early-stop gate (reused at three boundaries) and the single
collector/sink that drives the exit code.

## Deliverables

In `modules/rtl_test/control.py`:

- `EarlyStopGateMod` — `(payload, early_stop:str="post")` with module `Config` containing
  `phase:str` (one of `pre`/`comp`/`sim`). `payload` is `ctx` at `gate-pre`/`gate-comp`
  and `test_run` at `gate-sim`; the module reads only `payload["key"]` and is agnostic to
  the shape otherwise. Compares `early_stop` against `phase` using the ordering
  `pre < comp < sim < post`; if stop here → `("stop", {"key": payload["key"], "result":
  EarlyStopResults(f"Stopped early at {phase}")})`; else `("go", payload)`. Three node
  instances in the graph, differing only in `config.phase`.
  **Failure handling**: routing only; no exception caught, no log call. `("stop", ...)`
  is a normal terminal (not a failure) — distinct from the FAIL emitters in spec 05/06.
  See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
- `AggregateResultsMod` — `run(self, result)` accumulates the delivered `result`
  payload into `self._rows`. Receives from `fan-in-results` (spec 02) via the single
  `result` port; uses the `default` contract. `finalise()` prints the summary table
  (`key`/`test_name`, `result`, `desc`), and logs `ERROR` if any row's `result.is_pass()`
  is false.
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
- Aggregate: feeding N rows through `fan-in-results` (each arriving on `result`) produces
  a single summary; mix of PASS/SKIP/FAIL/NA correctly triggers the ERROR-level log (exit
  code 1 path).

## Acceptance criteria

- Tests pass.
- Aggregator + `any`-contract integration test from spec 02 confirms delivery from every
  wired terminal branch reaches `aggregate-results.result` in order.
- A toy 3-input `fan-in-results` test plus aggregator finalise reproduces an OR-accumulated
  exit code matching rtl_buddy's `exit_code |= 0 if is_pass() else 1` semantics.

## Notes

Adding a new terminal-result source means adding one edge in [06] to `fan-in.` — the
`fan-in-results` module signature (`**inputs`) and `aggregate-results`' signature are both
untouched.

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent
in the schema package from spec 01) rather than ad-hoc string compares.

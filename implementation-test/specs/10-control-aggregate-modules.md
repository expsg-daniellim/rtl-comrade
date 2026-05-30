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
- `AggregateResultsMod` — `run(self, **fired)` accumulates terminal-result payloads in
  `self._rows`; `finalise()` prints the summary table (`key`/`test_name`, `result`,
  `desc`), and logs `ERROR` if any row's `result.is_pass()` is false. Paired with the
  `merge` contract from spec 02.

Manifest entries per [06](../06-graph-yaml.md).

Tests in `modules/tests/test_control_aggregate.py`:
- Gate routing matches expected ordering across all four `early_stop` values for each of
  the three `phase` configurations.
- Aggregate: feeding N rows via varied port names produces a single summary; mix of
  PASS/SKIP/FAIL/NA correctly triggers ERROR-level log (exit code 1 path).

## Acceptance criteria

- Tests pass.
- Aggregator + merge integration test from spec 02 confirms `**fired` delivery from
  `merge` works end-to-end.
- A toy 3-port `merge` test plus aggregator finalise reproduces an OR-accumulated exit
  code matching rtl_buddy's `exit_code |= 0 if is_pass() else 1` semantics.

## Notes

`aggregate-results.run(self, **fired)` depends on **spec 00**'s `**kwargs` port-inference
probe having confirmed the harness supports the open port set. If that probe failed,
declare the eight ports explicitly (`skip=None, es_pre=None, …, post_plain=None,
post_uvm=None`) here.

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent
in the schema package from spec 01) rather than ad-hoc string compares.

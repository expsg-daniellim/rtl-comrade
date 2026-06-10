# Spec 10a: early-stop-gate (`EarlyStopGateMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md). Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Goal

Implement the cross-cutting early-stop gate, reused at three boundaries
(`gate-pre`/`gate-comp`/`gate-sim`).

## Deliverables

In `modules/rtl_test/control.py` — `EarlyStopGateMod`:

`(payload, early_stop:str="post")` with module `Config` containing `phase:str` (one of
`pre`/`comp`/`sim`). `payload` is `ctx` at `gate-pre`/`gate-comp` and `test_run` at
`gate-sim`; the module reads only `payload["key"]` and is agnostic to the shape otherwise.
Compares `early_stop` against `phase` using the ordering `pre < comp < sim < post`; if stop
here → `("stop", {"key": payload["key"], "result": EarlyStopResults(f"Stopped early at
{phase}")})` **and** `log.info("test_result", key=..., result="NA", desc=...)`; else
`("go", payload)`. Three node instances, differing only in `config.phase`. The `stop` port is
**unwired** (TODO #15) — the harness logs `no_destination` at INFO.
**Failure handling**: routing only; no exception, no `log.error` (a `stop` is a normal
terminal, not a failure). See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).

**Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:59-76` — the `RunDepth` early-stop checkpoints; enum at `test_runner.py:14-18`; `--early-stop` flag at `rtl_buddy.py:121`; `EarlyStopResults` at `runner/test_results.py:53-60`.

Manifest entries for `EarlyStopGateMod` per [06](../06-graph-yaml.md).

## Tests

`modules/tests/test_control.py`:

- Gate routing matches expected ordering across all four `early_stop` values for each of the
  three `phase` configurations; a `stop` also emits one `test_result` event at INFO.

## Acceptance criteria

- Tests pass.
- Both output ports (`go`, `stop`) are exercised across all four `early_stop` values for
  each `phase`; a `stop` emits one `test_result` event at INFO.

## Notes

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent in
the schema package from spec 01) rather than ad-hoc string compares.

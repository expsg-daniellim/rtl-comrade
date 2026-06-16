# Spec 10a: early-stop-gate (`EarlyStopGateMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](../03-module-catalog.md),
[05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node),
[07 item 27](../07-ambiguities-and-assumptions.md). Parent index:
[10 — Control module, git-status, and the summary logging plugin](10-control-aggregate-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module is the sole occupant of `modules/rtl_buddy/control.py`, so it has no
sibling specs appending to the same file.

## Goal

Implement the cross-cutting early-stop gate, reused at three boundaries
(`gate-pre`/`gate-comp`/`gate-sim`).

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
The `payload` port accepts either `ctx` (gate-pre/comp) or `test_run` (gate-sim) — the
module reads only `payload["key"]`.

```
contract:          default
config:            phase:str   (pre | comp | sim)
persistent_inputs: [early_stop]
inputs:            payload, early_stop:str = "post"
outputs:           go   → payload
                   stop → result
```

```python
class EarlyStopGateMod:
    @serde
    class Config:
        phase:str   # "pre" | "comp" | "sim"

    def __init__(self, config):
        self.phase = config.phase

    def run(self, payload, early_stop:str = "post"):
        order = ["pre", "comp", "sim", "post"]   # reuse rtl_buddy RunDepth
        if order.index(early_stop) <= order.index(self.phase):
            log.info("test_result", key=payload["key"], result="NA", desc=f"Stopped early at {self.phase}")
            return ("stop", { "key": payload["key"], "result": EarlyStopResults(f"Stopped early at {self.phase}") })
        return ("go", payload)
```

## Algorithm

1. Establish the phase ordering `order = ["pre", "comp", "sim", "post"]` (reuse rtl_buddy's
   `RunDepth` / a small schema equivalent — see Notes), where `self.phase` is this node
   instance's checkpoint and `early_stop` is the requested depth.
2. Branch: if `order.index(early_stop) <= order.index(self.phase)`, this run is stopped at or
   before this checkpoint → emit `("stop", {"key": payload["key"], "result":
   EarlyStopResults(f"Stopped early at {self.phase}")})` **and** `log.info("test_result",
   key=payload["key"], result="NA", desc=f"Stopped early at {self.phase}")` (the
   `SummaryProcessor` collects that event; the `stop` port itself is unwired). Otherwise emit
   `("go", payload)`.

The module reads only `payload["key"]` and is agnostic to whether `payload` is `ctx`
(gate-pre/comp) or `test_run` (gate-sim). No failure path — a `stop` is a normal terminal, not
an error.

## Deliverables

In `modules/rtl_buddy/control.py` — `EarlyStopGateMod`:

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
**Exit-code divergence (deliberate):** `EarlyStopResults` is NA, and `rtl_buddy` exits 1 on
`--early-stop` (`runner/test_results.py:53-60`; `rtl_buddy.py:206`). Plan B treats a user-requested
stop as a successful early exit, so this `log.info` (never `log.error`) leaves `handler.failure`
False → exit 0. Per-test verdict and summary row are unchanged. Recorded in
[07 — Notable divergences](../07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy).

**Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:59-76` — the `RunDepth` early-stop checkpoints; enum at `test_runner.py:14-18`; `--early-stop` flag at `rtl_buddy.py:121`; `EarlyStopResults` at `runner/test_results.py:53-60`.

**Manifest** — `EarlyStopGateMod` is the only plugin in the `rtl_buddy/control.py` block of
`modules/config.yaml`:

```yaml
- file: rtl_buddy/control.py
  plugins:
  - { name: early-stop-gate, class_name: EarlyStopGateMod }
```

## Tests

`modules/tests/test_control.py`. Fixtures: `Config(phase=…)`; `payload` dicts in both `ctx`
and `test_run` shapes (the module reads only `payload["key"]`); `logging_handler` to capture
the INFO `test_result` event and confirm no `failure`. Order is `pre < comp < sim < post`;
stop iff `order.index(early_stop) <= order.index(phase)`.

- Parametrised matrix — all three `phase` values × all four `early_stop` values (`pre`/`comp`/
  `sim`/`post`) → `("go", payload)` when `early_stop` is strictly after `phase`, else `("stop",
  {"key", "result": EarlyStopResults})`. Exercises both ports for every `phase`.
- `phase="comp", early_stop="comp"` (own-phase) → `("stop", …)` (boundary: inclusive `<=` —
  a gate stops at its own checkpoint) and emits exactly one `log.info("test_result",
  result="NA", desc="Stopped early at comp")`.
- `phase="comp", early_stop="post"` (default) → `("go", payload)` and emits **no**
  `test_result` event (boundary: the default `post` never stops any phase).
- A `stop` emits no `log.error`/`log.fatal` — `logging_handler.failure` stays `False` (a
  stop is a normal terminal, not a failure).
- `payload` agnosticism: a `ctx`-shaped payload at `phase="pre"` and a `test_run`-shaped
  payload at `phase="sim"` both route purely on `payload["key"]`.

## Acceptance criteria

- Tests pass.
- Both output ports (`go`, `stop`) are exercised across all four `early_stop` values for each
  `phase`: `go` forwards the `payload`; a `stop` emits one `test_result` event at INFO.
- The `modules/config.yaml` manifest entry `{ name: early-stop-gate, class_name: EarlyStopGateMod }`
  validates and the harness resolves `early-stop-gate` → `EarlyStopGateMod`.

## Constraints

- `Config.phase` is one of `pre`/`comp`/`sim`; the ordering is fixed `pre < comp < sim < post`.
  Reuse rtl_buddy's `RunDepth` ordering — do **not** ad-hoc string-compare.
- Stop iff `order.index(early_stop) <= order.index(self.phase)`: emit `("stop", {key, result:
  EarlyStopResults})` on the **unwired** `stop` port **and** `log.info("test_result",
  result="NA", desc=…)`. Otherwise emit `("go", payload)`.
- A `stop` is a **normal terminal, not a failure** — emit **no** `log.error`/`log.fatal`.
- Read only `payload["key"]`; stay agnostic to whether `payload` is `ctx` (gate-pre/comp) or
  `test_run` (gate-sim). Three node instances differ only by `config.phase`.

## Notes

The phase ordering should reuse rtl_buddy's `RunDepth` enum (or a small local equivalent in
the schema package from spec 01) rather than ad-hoc string compares.

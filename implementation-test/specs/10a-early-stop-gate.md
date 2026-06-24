# Spec 10a: early-stop-gate (`EarlyStopGateMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Control section](../03-module-catalog.md), [05 — Re-convergence](../05-branching-and-results.md#re-convergence-the-summary-is-a-logging-concern-not-a-graph-node), [07 item 27](../07-ambiguities-and-assumptions.md). Parent index: [idx-10 — Control module, git-status, and the summary logging plugin](../idx-10-control-aggregate.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module is the sole occupant of `modules/rtl_buddy/control.py`, so it has no sibling specs appending to the same file.

## Goal

Implement the cross-cutting early-stop gate, reused at three boundaries (`gate-pre`/`gate-comp`/`gate-sim`).

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. The gate takes **`**edges`** — the harness populates its keyed input ports from the graph edges wired to each instance (the non-definite-inputs support, `graph.py:95-97`). So one module serves all three instances: `gate-pre` is wired `{test}`; `gate-comp` is wired `{test, simv}` (the `simv` edge must travel through the gate so `expand-runs` downstream can join it); `gate-sim` is wired `{test, proc}`. On "go" it **co-gates** by forwarding *every* input edge on a same-named output port; on "stop" it drops them all and emits a result. Identity comes from the always-present `test` edge.

```
contract:          default (gate-pre: one keyed edge) / keyed_join (gate-comp: test+simv; gate-sim: test+proc)
config:            phase:str   (pre | comp | sim)
persistent_inputs: [early_stop]
inputs:            early_stop:str = "post", **edges   (keyed edges per instance: {test} for pre, {test, simv} for comp, {test, proc} for sim)
outputs:           <each input edge forwarded on its same-named port on "go">  +  stop → TestResult (self-keyed)
```

```python
class EarlyStopGateMod:
    @serde
    class Config:
        phase:str   # "pre" | "comp" | "sim"

    def __init__(self, config):
        self.phase = config.phase

    def run(self, early_stop:str = "post", **edges):   # edges: {port_name: payload}; always includes "test"
        order = [d.value for d in RunDepth]   # RunDepth (spec 01): pre < comp < sim < post
        if early_stop not in order:              # guard: reject an invalid --early-stop value
            log.fatal("invalid_early_stop", early_stop=early_stop, valid=order)
        test = edges["test"]
        if order.index(early_stop) <= order.index(self.phase):
            log.info("test_result", key=test.key, test_name=test.get_name(),
                     result="NA", desc=f"Stopped early at {self.phase}")
            yield ("stop", TestResult.early_stop(test.key, f"Stopped early at {self.phase}"))
        else:
            for name, payload in edges.items():   # forward every co-gated edge on its own port
                yield (name, payload)
```

## Algorithm

1. Establish the phase ordering from the `RunDepth` enum (spec [01](01-shared-schema.md), schema package): `order = [d.value for d in RunDepth]` → `["pre", "comp", "sim", "post"]`, where `self.phase` is this node instance's checkpoint and `early_stop` is the requested depth. Guard first: if `early_stop` is not one of the four phase tokens, `log.fatal("invalid_early_stop", …)` — the CLI edge is a bare `str` and the harness does not enum-validate it, so an invalid `--early-stop` value would otherwise raise an uncaught `ValueError` at `order.index(early_stop)`.
2. Branch: if `order.index(early_stop) <= order.index(self.phase)`, this run is stopped at or before this checkpoint → emit `("stop", TestResult.early_stop(test.key, f"Stopped early at {self.phase}"))` (a self-keyed `TestResult`, `type_=EARLY_STOP`, verdict `NA`) **and** `log.info("test_result", key=test.key, test_name=test.get_name(), result="NA", desc=f"Stopped early at {self.phase}")` (the `SummaryProcessor` collects that event — `test_name` is its first column; the `stop` port itself is unwired). Otherwise **forward every input edge** on its same-named port: `for name, payload in edges.items(): yield (name, payload)` — this co-gates whatever flows through the gate (`{test}` at pre, `{test, simv}` at comp, `{test, proc}` at sim), so a stop drops them all together and no downstream join dangles.

`edges` always contains `"test"` (identity); the module reads `edges["test"].key` and `.value`. The only failure path is the `log.fatal` guard on an invalid `early_stop`; a `stop` itself is a normal terminal, not an error.

## Deliverables

In `modules/rtl_buddy/control.py` — `EarlyStopGateMod`:

`(early_stop:str="post", **edges)` with module `Config` containing `phase:str` (one of `pre`/`comp`/`sim`). One module serves all three node instances, which differ only by `config.phase` and the edges wired to them: `gate-pre` `{test}` (contract `default`); `gate-comp` `{test, simv}` and `gate-sim` `{test, proc}` (both `keyed_join`). Identity comes from `edges["test"]` (always present). Behaviour — the `early_stop` guard, the `pre < comp < sim < post` stop/forward branch, and the co-gating — is specified under [Algorithm](#algorithm) and [Constraints](#constraints). The `stop` port is **unwired**, so the harness logs `no_destination` at INFO.
**Failure handling**: routing only — no `log.error` (a `stop` is a normal terminal, not a failure). One guard: an `early_stop` value outside `{pre,comp,sim,post}` → `log.fatal("invalid_early_stop", …)` (harness exit 1), since the CLI edge is a bare `str` the harness does not enum-validate. See [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site).
**Exit-code divergence (deliberate):** the early-stop result is NA, and `rtl_buddy` exits 1 on `--early-stop` (`runner/test_results.py:53-60`; `rtl_buddy.py:206`). This plan treats a user-requested stop as a successful early exit, so this `log.info` (never `log.error`) leaves `handler.failure` False → exit 0. The per-test `NA` verdict is unchanged, but the `desc` wording diverges: this plan emits `"Stopped early at <phase>"` with the phase token (`pre`/`comp`/`sim`), where rtl_buddy emits `preproc`/`compile`/`sim` — matching only for `sim`. Recorded in [07 — Notable divergences](../07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy).

**Compatibility source:** `rtl_buddy/src/rtl_buddy/runner/test_runner.py:59-76` — the `RunDepth` early-stop checkpoints; enum at `test_runner.py:14-18`; `--early-stop` flag at `rtl_buddy.py:121`; `EarlyStopResults` at `runner/test_results.py:53-60`.

**Manifest** — `EarlyStopGateMod` is the only plugin in the `rtl_buddy/control.py` block of `modules/config.yaml`:

```yaml
- file: rtl_buddy/control.py
  plugins:
  - { name: early-stop-gate, class_name: EarlyStopGateMod }
```

## Tests

`modules/tests/test_control.py`. Fixtures: `Config(phase=…)`; a `test` edge dict (`{key, value}`, value with `get_name`) and a `proc` edge dict (for the gate-sim co-gating case); `logging_handler` to capture the INFO `test_result` event and confirm no `failure`. Order is `pre < comp < sim < post`; stop iff `order.index(early_stop) <= order.index(phase)`. Drive `run(early_stop=…, **edges)` directly (e.g. `run(early_stop="sim", test=…, proc=…)`).

- Parametrised matrix — all three `phase` values × all four `early_stop` values (`pre`/`comp`/ `sim`/`post`), each wired with its instance's edges (`{test}` for `pre`, `{test, simv}` for `comp`, `{test, proc}` for `sim`) → forwards **every** input edge on its same-named port when `early_stop` is strictly after `phase`, else `("stop", TestResult.early_stop(key, …))`. Exercises both branches for every `phase`.
- **Co-gating (gate-comp / gate-sim)** — `gate-comp` wired `{test, simv}` and `gate-sim` wired `{test, proc}`: on "go" (`early_stop` strictly after the phase) forwards **both** edges (`("test", test)`+`("simv", simv)`, resp. `("test", test)`+`("proc", proc)`); on a stop (`early_stop ≤ phase`) emits only `("stop", TestResult.early_stop(test.key, …))`, dropping both (boundary: `**edges` co-gating — a stop never leaks a partial group to the downstream join).
- `phase="comp", early_stop="comp"` (own-phase) → `("stop", …)` (boundary: inclusive `<=` — a gate stops at its own checkpoint) and emits exactly one `log.info("test_result", result="NA", desc="Stopped early at comp")`.
- `phase="comp", early_stop="post"` (default) → forwards its input edge(s) and emits **no** `test_result` event (boundary: the default `post` never stops any phase).
- A `stop` emits no `log.error`/`log.fatal` — `logging_handler.failure` stays `False` (a stop is a normal terminal, not a failure).
- `early_stop="bogus"` (not a phase token) → `log.fatal("invalid_early_stop", …)` → `pytest.raises(typer.Exit)` (boundary: invalid `--early-stop` value, since the CLI edge is an unvalidated `str`).

## Acceptance criteria

- Tests pass.
- Co-gating exercised across all four `early_stop` values for each `phase`: on "go" the gate forwards **every** input edge on its same-named port (`{test}` at gate-pre, `{test, simv}` at gate-comp, `{test, proc}` at gate-sim); a `stop` drops them all and emits one `test_result` event at INFO.
- The `modules/config.yaml` manifest entry `{ name: early-stop-gate, class_name: EarlyStopGateMod }` validates and the harness resolves `early-stop-gate` → `EarlyStopGateMod`.

## Constraints

- `Config.phase` is one of `pre`/`comp`/`sim`; the ordering is fixed `pre < comp < sim < post`. Source it from the `RunDepth` enum (spec [01](01-shared-schema.md), schema package) — `order = [d.value for d in RunDepth]`; do **not** re-list the tokens or ad-hoc string-compare.
- Stop iff `order.index(early_stop) <= order.index(self.phase)`: emit `("stop", TestResult.early_stop(test.key, …))` on the **unwired** `stop` port **and** `log.info("test_result", result="NA", desc=…)`. Otherwise forward **every** input edge on its same-named port (`for name, payload in edges.items(): yield (name, payload)`) — co-gate all so a stop can't dangle a downstream join.
- A `stop` is a **normal terminal, not a failure** — emit **no** `log.error`/`log.fatal`.
- Read identity from `edges["test"]` (always wired). Accept `**edges` (non-definite inputs, `graph.py:95-97`); the graph wires `{test}` at `gate-pre`, `{test, simv}` at `gate-comp`, and `{test, proc}` at `gate-sim`. Contract is per-instance: `default` (one keyed edge) / `keyed_join` (two or more). The three instances differ by `config.phase` and the edges wired to them.
- Guard `early_stop` against `{pre,comp,sim,post}` → `log.fatal("invalid_early_stop", …)` on an invalid value (the CLI edge is a bare `str`; the harness does not enum-validate it). A `Literal["pre","comp","sim","post"]` annotation is an acceptable equivalent only if the harness enforces it; the explicit membership guard is the reliable mechanism.

## Notes

The phase ordering reuses the `RunDepth` enum delivered by spec [01](01-shared-schema.md) (schema package, `run_depth.py`) rather than ad-hoc string compares — `order = [d.value for d in RunDepth]`.

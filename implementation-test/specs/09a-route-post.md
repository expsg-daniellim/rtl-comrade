# Spec 09a: route-post (`RoutePostMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RoutePostMod`
reads `ctx["test"].uvm`).
**References:** [03 — Post-processing section](../03-module-catalog.md). Parent index:
[09 — Post-processing modules](09-post-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/sim.py`, shared with the sim-cycle modules
(`08a`–`08f`, index [08](08-sim-cycle-modules.md)) and the post modules (`09a`–`09c`, index
[09](09-post-modules.md)); coordinate shared imports and helpers with those specs.

## Goal

Classify the post-processing path: uvm vs plain.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
The payload at this stage is the post-sim `test_run` record ([02 — Shape 1b](../02-payload-conventions.md)).

```
contract: default
inputs:   test_run
outputs:  uvm   → test_run
          plain → test_run
```

```python
class RoutePostMod:
    def run(self, test_run):
        return ("uvm", test_run) if test_run["test"].uvm is not None else ("plain", test_run)
```

## Algorithm

1. Branch on UVM presence: emit `("uvm", test_run)` when `test_run["test"].uvm is not None` (a
   `UVMConfig`), else `("plain", test_run)`. Pure classifier — no scheduling, no failure path.

## Deliverables

In `modules/rtl_test/sim.py` (continuing from spec 08):

- `RoutePostMod` — `(ctx)` → `("uvm", ctx)` if `ctx["test"].uvm is not None` else
  `("plain", ctx)`. `ctx["test"].uvm` is `UVMConfig | None` per spec
  [01b](01b-suite-schema.md). Pure data classifier; no scheduling.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:293-298` — the `if self.test_cfg.uvm:` dispatch in `VlogSim.post`.

**Manifest** — append to the `- file: rtl_test/sim.py` block in `modules/config.yaml`
(opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: route-post, class_name: RoutePostMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `test_run` dicts whose `test.uvm` is a `UVMConfig`
or `None`. Pure classifier — no `logging_handler`.

- `test_run["test"].uvm` is a `UVMConfig` → emits `("uvm", test_run)` (the same object).
- `test_run["test"].uvm is None` → emits `("plain", test_run)`.
- `test_run["test"].uvm` is a `UVMConfig` with all-zero thresholds (`max_warns=0,
  max_errors=0`) → still emits `("uvm", test_run)` (boundary: routes on `is not None`, not
  truthiness — a zero-threshold config is still present).
- Both ports carry `test_run` through unchanged (identity passthrough, no mutation).

## Acceptance criteria

- Tests pass.
- Both output ports (`uvm`, `plain`) are exercised, routing on `ctx["test"].uvm`.

## Constraints

- Pure classifier on `test_run["test"].uvm is not None` → `("uvm", test_run)` else `("plain",
  test_run)`. No scheduling, no failure path, no log call.
- Keep the route-post + two-parser split (atomic-by-function) — do **not** collapse the UVM and
  plain parsing back into this node.
- Use string-literal port names (`uvm`/`plain`).

## Notes

`route-post` + two-parsers is the example to keep returning to for "atomic-by-function,
not by signature" — make sure the implementation preserves that split rather than
collapsing them back into one node.

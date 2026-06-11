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

In `modules/tests/test_post.py`:

- `route-post` routes correctly on `uvm` presence/absence.

## Acceptance criteria

- Tests pass.
- Both output ports (`uvm`, `plain`) are exercised, routing on `ctx["test"].uvm`.

## Notes

`route-post` + two-parsers is the example to keep returning to for "atomic-by-function,
not by signature" — make sure the implementation preserves that split rather than
collapsing them back into one node.

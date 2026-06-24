# Spec 09a: route-post (`RoutePostMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RoutePostMod` reads `test.uvm`).
**References:** [03 — Post-processing section](../03-module-catalog.md). Parent index: [idx-09 — Post-processing modules](../idx-09-post.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/sim.py`, which is created by spec [`08a`](08a-expand-runs.md) — append, do not overwrite. The file is shared with the sim-cycle modules (`08a`–`08f`, index [idx-08](../idx-08-sim-cycle.md)) and the post modules (`09a`–`09c`, index [idx-09](../idx-09-post.md)); coordinate shared imports and helpers with those specs.

## Goal

Classify the post-processing path: uvm vs plain.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes. `test` + `proc` are joined by key here, and **co-routed** to one parser branch (the documented split exception — see Notes).

```
contract:        keyed_join
contract_config: key_field: key
inputs:          test, proc   (joined by key)
outputs:         uvm_test,   uvm_proc     (UVM branch → parse-uvm-log)
                 plain_test, plain_proc   (plain branch → parse-log)
```

```python
class RoutePostMod:
    def run(self, test, proc):   # test + proc co-routed to one parser branch
        if test.uvm is not None:
            yield ("uvm_test", test)
            yield ("uvm_proc", proc)
        else:
            yield ("plain_test", test)
            yield ("plain_proc", proc)
```

## Algorithm

1. Branch on UVM presence: when `test.uvm is not None` (a `UVMConfig`), forward `test`+`proc` on the UVM branch (`uvm_test`/`uvm_proc` → `parse-uvm-log`), else on the plain branch (`plain_test`/`plain_proc` → `parse-log`). Pure classifier — no scheduling, no failure path. `test` and `proc` are **co-routed** (both go to the same parser) so the unchosen parser's `keyed_join` can't dangle.

## Deliverables

In `modules/rtl_buddy/sim.py` (continuing from spec 08):

- `RoutePostMod` — `(test, proc)`, `keyed_join` → forwards `test`+`proc` on the UVM branch (`uvm_test`/`uvm_proc`) if `test.uvm is not None` else the plain branch (`plain_test`/`plain_proc`). `test.uvm` is `UVMConfig | None` per spec [01b](01b-suite-schema.md). Pure data classifier; no scheduling. `test`+`proc` are co-routed (the documented split exception).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:293-298` — the `if self.test_cfg.uvm:` dispatch in `VlogSim.post`.

**Manifest** — append to the `- file: rtl_buddy/sim.py` block in `modules/config.yaml` (opened by [`08a`](08a-expand-runs.md); append, don't re-create):

```yaml
  - { name: route-post, class_name: RoutePostMod }
```

## Tests

In `modules/tests/test_post.py`. Fixtures: `test` (`{key, value}`, value with `.uvm` a `UVMConfig` or `None`) and `proc` dict fixtures. Pure classifier — no `logging_handler`. Drive `run(test, proc)` directly.

- `test.uvm` is a `UVMConfig` → emits `("uvm_test", test)` then `("uvm_proc", proc)` (same objects).
- `test.uvm is None` → emits `("plain_test", test)` then `("plain_proc", proc)`.
- `test.uvm` is a `UVMConfig` with all-zero thresholds (`max_warns=0, max_errors=0`) → still routes UVM (boundary: routes on `is not None`, not truthiness — a zero-threshold config is still present).
- The chosen branch carries `test`+`proc` through unchanged (identity passthrough, no mutation); the other branch emits nothing.

## Acceptance criteria

- Tests pass.
- Both branches (`uvm_test`/`uvm_proc`, `plain_test`/`plain_proc`) are exercised, routing on `test.uvm`; each carries `test`+`proc` unchanged.
- No failure path: pure classifier, no `log` call.
- The `modules/config.yaml` manifest entry `{ name: route-post, class_name: RoutePostMod }` validates and the harness resolves `route-post` → `RoutePostMod`.

## Constraints

- `keyed_join` over `test`+`proc` (key_field `key`). Pure classifier on `test.uvm is not None` → forward both edges on the UVM branch else the plain branch. No scheduling, no failure path, no log call.
- Keep the route-post + two-parser split (atomic-by-function) — do **not** collapse the UVM and plain parsing back into this node.
- Use string-literal port names (`uvm_test`/`uvm_proc`/`plain_test`/`plain_proc`).

## Notes

`route-post` + two-parsers is the example to keep returning to for "atomic-by-function, not by signature" — make sure the implementation preserves that split rather than collapsing them back into one node.

**Co-routing exception.** This is the one node where two edges (`test`+`proc`) are *co-routed* — both always travel to the *same* parser. The split therefore uses four ports (two edges × two branches: `uvm_test`/`uvm_proc`, `plain_test`/`plain_proc`) rather than splitting the routing decision per edge. Routing the two edges independently would buy nothing (the choice is identical for both) and would dangle the unchosen parser's `keyed_join` if only one edge arrived. Co-routing is correct here precisely because the two edges share one routing decision — unlike edges whose fields have independent lifecycles, which is why those are split.

# Spec 09a: route-post (`RoutePostMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RoutePostMod`
reads `ctx["test"].uvm`).
**References:** [03 — Post-processing section](../03-module-catalog.md). Parent index:
[09 — Post-processing modules](09-post-modules.md).

## Goal

Classify the post-processing path: uvm vs plain.

## Deliverables

In `modules/rtl_test/sim.py` (continuing from spec 08):

- `RoutePostMod` — `(ctx)` → `("uvm", ctx)` if `ctx["test"].uvm is not None` else
  `("plain", ctx)`. `ctx["test"].uvm` is `UVMConfig | None` per spec
  [01b](01b-suite-schema.md). Pure data classifier; no scheduling.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:293-298` — the `if self.test_cfg.uvm:` dispatch in `VlogSim.post`.

Manifest entries per [06](../06-graph-yaml.md).

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

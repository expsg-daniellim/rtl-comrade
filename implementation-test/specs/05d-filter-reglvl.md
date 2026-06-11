# Spec 05d: filter-reglvl (`FilterRegLvlMod`)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md) (builder schema —
`FilterRegLvlMod` consumes `RtlBuilderConfig`), spec [01b](01b-suite-schema.md)
(`TestConfig.get_reglvl`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, shared with the setup chain
(`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`,
index [05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared
imports and helpers with those specs.

## Goal

Route each `ctx` keep/skip based on whether the test's regression level falls inside the
configured `[start_level, reg_level]` window.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          default
persistent_inputs: [builder_cfg, reg_level, start_level]
inputs:            ctx, builder_cfg, reg_level=None, start_level=None
outputs:           keep → ctx
                   skip → result
```

```python
class FilterRegLvlMod:
    def run(self, ctx, builder_cfg, reg_level = None, start_level = None):
        lvl = ctx["test"].get_reglvl(builder_cfg.get_name())
        if (reg_level is not None and lvl > reg_level) or (start_level is not None and lvl < start_level):
            return ("skip", { "key": ctx["key"], "result": SkipResults(desc=...) })
        return ("keep", ctx)
```

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `FilterRegLvlMod` — `(ctx, builder_cfg, reg_level=None, start_level=None)` →
  `("keep", ctx)` if level inside `[start_level, reg_level]` window (or both `None`),
  else `("skip", {"key": ctx["key"], "result": SkipResults(desc)})`. The per-test
  level comes from `ctx["test"].get_reglvl(builder_cfg.get_name())` (mirrors
  `rtl_buddy/src/rtl_buddy/rtl_buddy.py:350`) — only the builder *name* is needed,
  not the full config object, but the persistent port carries the whole
  `RtlBuilderConfig` (see spec [01a](01a-builder-schema.md)) because the same
  payload feeds `cc-build`, `seed`, and `sim-build` downstream. No failure path
  (SKIP is a routing decision and is pass-like; no log call).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:349-357` — `_do_test_suite` level filter; `get_reglvl` at `config/test.py:287-299`; `SkipResults` at `runner/test_results.py:71-78`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_selection.py`:

- `filter` keep/skip routing matches rtl_buddy `_do_test_suite` level-filter logic
  (both `None` → keep; level inside window → keep; level outside window → skip with
  `SkipResults`).

## Acceptance criteria

- Tests pass.
- Both output ports (`keep`, `skip`) are exercised; the skip path emits `SkipResults`.

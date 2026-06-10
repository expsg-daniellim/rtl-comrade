# Spec 05d: filter-reglvl (`FilterRegLvlMod`)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md) (builder schema —
`FilterRegLvlMod` consumes `RtlBuilderConfig`), spec [01b](01b-suite-schema.md)
(`TestConfig.get_reglvl`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Goal

Route each `ctx` keep/skip based on whether the test's regression level falls inside the
configured `[start_level, reg_level]` window.

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

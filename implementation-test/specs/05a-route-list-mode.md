# Spec 05a: route-list-mode (`RouteListModeMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`SuiteConfig`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Goal

Classify the run into list-mode vs run-mode at the front of the test stream.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `RouteListModeMod` — `(suite_cfg, list:bool=False)` → emits `("list", suite_cfg)` if
  `list` else `("run", suite_cfg)`. Pure data classifier.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:182-184` — the `if list_tests:` branch in `do_cmd_test`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_selection.py`:

- `list=True` → emits `("list", suite_cfg)`; `list=False` → emits `("run", suite_cfg)`.

## Acceptance criteria

- Tests pass.
- Both output ports (`list`, `run`) are exercised and route on the `list` flag.

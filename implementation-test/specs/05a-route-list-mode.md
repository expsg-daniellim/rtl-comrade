# Spec 05a: route-list-mode (`RouteListModeMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`SuiteConfig`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Goal

Classify the run into list-mode vs run-mode at the front of the test stream.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   suite_cfg, list:bool = False
outputs:  run  → suite_cfg
          list → suite_cfg
```

```python
class RouteListModeMod:
    def run(self, suite_cfg, list:bool = False):
        return ("list", suite_cfg) if list else ("run", suite_cfg)
```

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

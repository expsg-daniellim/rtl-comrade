# Spec 05b: list-test-names (`ListTestNamesMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`SuiteConfig`).
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

Print the suite's test names in declaration order — the list-mode terminal sink.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   suite_cfg
outputs:  none  (terminal sink)
```

```python
class ListTestNamesMod:
    def run(self, suite_cfg):
        print("  ".join(suite_cfg.get_test_names()))   # terminal: emits nothing
```

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `ListTestNamesMod` — `(suite_cfg)` → prints `"  ".join(suite_cfg.get_test_names())`
  (spec [01b](01b-suite-schema.md) — returns `list[str]` of test names in declaration
  order) and emits nothing. Terminal sink.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:183` — the `typer.echo` of `get_test_names()`; `get_test_names` at `config/suite.py:69-76`.

Manifest entries per [06](../06-graph-yaml.md).

## Tests

In `modules/tests/test_selection.py`:

- `list-names` prints expected names (declaration order, two-space joined).

## Acceptance criteria

- Tests pass.
- Prints test names in declaration order and emits nothing (terminal sink).

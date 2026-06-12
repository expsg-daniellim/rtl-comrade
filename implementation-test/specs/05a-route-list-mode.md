# Spec 05a: route-list-mode (`RouteListModeMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`SuiteConfig`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index:
[05 — Selection and expansion modules](05-selection-expansion-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

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

## Algorithm

1. Branch on the `list` flag: emit `("list", suite_cfg)` when `list` is true, else
   `("run", suite_cfg)`. Pure classifier — no failure path.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `RouteListModeMod` — `(suite_cfg, list:bool=False)` → emits `("list", suite_cfg)` if
  `list` else `("run", suite_cfg)`. Pure data classifier.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:182-184` — the `if list_tests:` branch in `do_cmd_test`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: route-list-mode, class_name: RouteListModeMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: a `suite_cfg` fixture (and an empty-suite
one); pure classifier otherwise.

- `(suite_cfg, list=True)` → emits `("list", suite_cfg)` (the same object, unchanged).
- `(suite_cfg, list=False)` → emits `("run", suite_cfg)`.
- `(suite_cfg)` with `list` omitted (default `False`) → emits `("run", suite_cfg)` (boundary:
  default arg).
- `(empty_suite_cfg, list=False)` → emits `("run", empty_suite_cfg)` unchanged (boundary: the
  classifier never inspects suite contents).

## Acceptance criteria

- Tests pass.
- Both output ports (`list`, `run`) are exercised and route on the `list` flag.

## Constraints

- Pure classifier: both ports carry `suite_cfg` unchanged. No failure path, no log call.
- Emit on string-literal port names (`list`/`run`) so `definite_emits` holds; stay
  graph-agnostic.

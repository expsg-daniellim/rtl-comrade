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
`a69d962`). This module appends to `modules/rtl_test/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

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

## Algorithm

1. Read the test's level: `lvl = ctx["test"].get_reglvl(builder_cfg.get_name())` — only the
   builder *name* is needed; the whole `RtlBuilderConfig` rides the persistent port because the
   same payload feeds `cc-build`/`seed`/`sim-build` downstream.
2. Test the window: if `reg_level is not None and lvl > reg_level`, or `start_level is not None
   and lvl < start_level`, the level is outside `[start_level, reg_level]` → emit
   `("skip", {"key": ctx["key"], "result": SkipResults(desc=...)})`.
3. Otherwise (inside the window, or both bounds `None`) emit `("keep", ctx)`.

No failure path: SKIP is a pass-like routing decision, not an error, and emits no log call.

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

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: filter-reglvl, class_name: FilterRegLvlMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: a `ctx` fixture whose `test.get_reglvl(name)`
returns a controlled int; a `builder_cfg` fixture with `get_name()`. No `logging_handler`
needed (SKIP is not an error).

- `(ctx, builder_cfg, reg_level=None, start_level=None)`, any `lvl` → emits `("keep", ctx)`
  (both bounds `None` keeps every test).
- `lvl` strictly inside `[start_level, reg_level]` (e.g. `lvl=3`, window `[1, 5]`) → emits
  `("keep", ctx)`.
- `lvl == reg_level` and `lvl == start_level` (window edges) → emits `("keep", ctx)`
  (boundary: window is inclusive, `> / <` are strict).
- `lvl > reg_level` (e.g. `lvl=6`, `reg_level=5`) → emits `("skip", {"key": ctx["key"],
  "result": SkipResults})` (boundary: above the upper bound).
- `lvl < start_level` (e.g. `lvl=0`, `start_level=1`) → emits `("skip", {"key": ctx["key"],
  "result": SkipResults})` (boundary: below the lower bound).

## Acceptance criteria

- Tests pass.
- Both output ports (`keep`, `skip`) are exercised: `keep` forwards `ctx`, and the `skip`
  diversion path emits a `SkipResults` `result`.
- The `modules/config.yaml` manifest entry `{ name: filter-reglvl, class_name: FilterRegLvlMod }`
  validates and the harness resolves `filter-reglvl` → `FilterRegLvlMod`.

## Constraints

- Window test is `[start_level, reg_level]`; when both bounds are `None`, every test is kept.
- Pass only the builder **name** to `get_reglvl(builder_cfg.get_name())`; the persistent port
  carries the whole `RtlBuilderConfig` because the same payload feeds `cc-build`/`seed`/
  `sim-build` downstream.
- SKIP is a **pass-like routing decision, not a failure** — emit `("skip", {key, result:
  SkipResults})` with **no** `log.error`/`log.critical`. The `skip` terminal port is unwired
  (TODO #15); still emit on it.
- Use string-literal port names (`keep`/`skip`); stay graph-agnostic.

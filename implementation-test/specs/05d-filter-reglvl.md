# Spec 05d: filter-reglvl (`FilterRegLvlMod`)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md) (builder schema — `FilterRegLvlMod` consumes `RtlBuilderConfig`), spec [01b](01b-suite-schema.md) (`TestConfig.get_reglvl`).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index: [idx-05 — Selection and expansion modules](../idx-05-selection-expansion.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Route each `test` edge — forward or skip — based on whether the test's regression level falls inside the configured `[start_level, reg_level]` window.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract:          default
persistent_inputs: [builder_cfg, reg_level, start_level]
inputs:            test, builder_cfg, reg_level=None, start_level=None
outputs:           test → TestConfig (self-keyed)   (the test edge, forwarded)
                   skip → TestResult (self-keyed)
```

```python
class FilterRegLvlMod:
    def run(self, test:TestConfig, builder_cfg:RtlBuilderConfig, reg_level:int | None = None, start_level:int | None = None):
        lvl = test.get_reglvl(builder_cfg.get_name())
        if reg_level is not None and lvl > reg_level:
            desc = f"lvl {lvl} > cmd end_level {reg_level}"          # rtl_buddy.py:353
        elif start_level is not None and lvl < start_level:
            desc = f"lvl {lvl} < cmd start_level {start_level}"      # rtl_buddy.py:357
        else:
            return ("test", test)
        result = TestResult.skip(test.key, test.get_name(), desc)
        return ("skip", result)
```

## Algorithm

1. Read the test's level: `lvl = test.get_reglvl(builder_cfg.get_name())` — only the builder *name* is read off the port (which carries the whole `RtlBuilderConfig`; see Constraints).
2. Test the window. Above the upper bound (`reg_level is not None and lvl > reg_level`) → `desc = f"lvl {lvl} > cmd end_level {reg_level}"`; below the lower bound (`start_level is not None and lvl < start_level`) → `desc = f"lvl {lvl} < cmd start_level {start_level}"` — the two distinct rtl_buddy messages (`rtl_buddy.py:353,357`). Build `result = TestResult.skip(test.key, test.get_name(), desc)` (a self-keyed `TestResult`, `type_=SKIP`) and emit `("skip", result)` — the outcome rides the `TestResult` to `results-summary`.
3. Otherwise (inside the window, or both bounds `None`) forward the test edge unchanged: emit `("test", test)`.

No failure path: a skip is a routing decision, not an error — it emits its `TestResult` on the `skip` port (→ `results-summary`), never `log.error`.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- `FilterRegLvlMod` — `(test, builder_cfg, reg_level=None, start_level=None)` → `("test", test)` (forward the test edge unchanged) if level inside `[start_level, reg_level]` window (or both `None`), else `("skip", TestResult.skip(test.key, test.get_name(), desc))`. The per-test level comes from `test.get_reglvl(builder_cfg.get_name())` (mirrors `rtl_buddy/src/rtl_buddy/rtl_buddy.py:350`) — only the builder *name* is read off the port (see Constraints for why it still carries the whole `RtlBuilderConfig`). On skip it emits its `TestResult` on the `skip` port (→ `results-summary`). No failure path (a skip is not an error).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:349-357` — `_do_test_suite` level filter; `get_reglvl` at `config/test.py:287-299`; `SkipResults` at `runner/test_results.py:71-78`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: filter-reglvl, class_name: FilterRegLvlMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: a `test` edge fixture (`{key, value}`) whose `value.get_reglvl(name)` returns a controlled int; a `builder_cfg` fixture with `get_name()`; `logging_handler` to assert the skip path keeps `failure` `False`.

- `(test, builder_cfg, reg_level=None, start_level=None)`, any `lvl` → emits `("test", test)` (both bounds `None` keeps every test); no log.
- `lvl` strictly inside `[start_level, reg_level]` (e.g. `lvl=3`, window `[1, 5]`) → emits `("test", test)`; no log.
- `lvl == reg_level` and `lvl == start_level` (window edges) → emits `("test", test)` (boundary: window is inclusive, `> / <` are strict).
- `lvl > reg_level` (e.g. `lvl=6`, `reg_level=5`) → emits `("skip", TestResult.skip(test.key, test.get_name(), desc))` (a `TestResult`, `type_=SKIP`); `logging_handler.failure is False` (boundary: above the upper bound; SKIP does not drive exit).
- `lvl < start_level` (e.g. `lvl=0`, `start_level=1`) → emits `("skip", TestResult.skip(test.key, test.get_name(), desc))` (boundary: below the lower bound).

## Acceptance criteria

- Tests pass.
- Both output ports (`test`, `skip`) are exercised: `test` forwards the `test` edge unchanged, and the `skip` diversion path emits a `TestResult.skip(...)` `TestResult` (`type_=SKIP`) on the `skip` port (→ `results-summary`, spec [10d](10d-summarise-results.md)) with no exit contribution.
- The `modules/config.yaml` manifest entry `{ name: filter-reglvl, class_name: FilterRegLvlMod }` validates and the harness resolves `filter-reglvl` → `FilterRegLvlMod`.

## Constraints

- Window test is `[start_level, reg_level]`; when both bounds are `None`, every test is kept.
- Pass only the builder **name** into `get_reglvl(builder_cfg.get_name())`, and read nothing else off the port. It carries the whole `RtlBuilderConfig` — `resolve-builder`'s single output (spec [01a](01a-builder-schema.md)) — rather than a bare name simply because there is no name-only port; minting one for this node alone would add a projection node for no benefit.
- SKIP is a **routing decision, not a failure** — on skip, emit `("skip", TestResult.skip(test.key, test.get_name(), desc))` (a self-keyed `TestResult`, `type_=SKIP`); a skip is not an error, so **never** `log.error`/`log.fatal`. The `skip` port is wired to `results-summary` (spec [10d](10d-summarise-results.md)).
- Forward the test edge unchanged on the `test` port (`("test", test)`); `test` is the bare self-keyed `TestConfig`, so read fields directly (`test.get_reglvl(...)`, `test.key`).
- Use string-literal port names (`test`/`skip`); stay graph-agnostic.

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
outputs:           test → {key, value}   (the test edge, forwarded)
                   skip → {key, result}
```

```python
class FilterRegLvlMod:
    def run(self, test, builder_cfg, reg_level = None, start_level = None):
        lvl = test["value"].get_reglvl(builder_cfg.get_name())
        if reg_level is not None and lvl > reg_level:
            desc = f"lvl {lvl} > cmd end_level {reg_level}"          # rtl_buddy.py:352
        elif start_level is not None and lvl < start_level:
            desc = f"lvl {lvl} < cmd start_level {start_level}"      # rtl_buddy.py:355
        else:
            return ("test", test)
        result = SkipResults(desc=desc)
        log.info("test_result", key=test["key"], test_name=test["value"].get_name(),  # SKIP is pass-like → INFO (no exit)
                 result=result.results["result"], desc=result.results["desc"])
        return ("skip", { "key": test["key"], "result": result })
```

## Algorithm

1. Read the test's level: `lvl = test["value"].get_reglvl(builder_cfg.get_name())` — only the builder *name* is needed; the whole `RtlBuilderConfig` rides the persistent port because the same payload feeds `cc-build`/`seed`/`sim-build` downstream.
2. Test the window. Above the upper bound (`reg_level is not None and lvl > reg_level`) → `desc = f"lvl {lvl} > cmd end_level {reg_level}"`; below the lower bound (`start_level is not None and lvl < start_level`) → `desc = f"lvl {lvl} < cmd start_level {start_level}"` — the two distinct rtl_buddy messages (`rtl_buddy.py:352,355`). Build `result = SkipResults(desc=desc)`, log it directly as `log.info("test_result", key=test["key"], result=..., desc=...)` (SKIP is pass-like, so **INFO** — it does **not** drive the exit), and emit `("skip", {"key": test["key"], "result": result})`.
3. Otherwise (inside the window, or both bounds `None`) forward the test edge unchanged: emit `("test", test)`.

No failure path: SKIP is a pass-like routing decision, not an error — it logs `test_result` at INFO (collected by `SummaryProcessor`), never `log.error`.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- `FilterRegLvlMod` — `(test, builder_cfg, reg_level=None, start_level=None)` → `("test", test)` (forward the test edge unchanged) if level inside `[start_level, reg_level]` window (or both `None`), else `("skip", {"key": test["key"], "result": SkipResults(desc)})`. The per-test level comes from `test["value"].get_reglvl(builder_cfg.get_name())` (mirrors `rtl_buddy/src/rtl_buddy/rtl_buddy.py:350`) — only the builder *name* is needed, not the full config object, but the persistent port carries the whole `RtlBuilderConfig` (see spec [01a](01a-builder-schema.md)) because the same payload feeds `cc-build`, `seed`, and `sim-build` downstream. On skip it logs `test_result` at INFO directly (`log.info("test_result", key, result, desc)`) so `SummaryProcessor` collects the row; SKIP is pass-like, so it never `log.error`s / drives the exit. No other failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:349-357` — `_do_test_suite` level filter; `get_reglvl` at `config/test.py:287-299`; `SkipResults` at `runner/test_results.py:71-78`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: filter-reglvl, class_name: FilterRegLvlMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: a `test` edge fixture (`{key, value}`) whose `value.get_reglvl(name)` returns a controlled int; a `builder_cfg` fixture with `get_name()`; `logging_handler` to assert the skip path logs one INFO `test_result` and keeps `failure` `False`.

- `(test, builder_cfg, reg_level=None, start_level=None)`, any `lvl` → emits `("test", test)` (both bounds `None` keeps every test); no log.
- `lvl` strictly inside `[start_level, reg_level]` (e.g. `lvl=3`, window `[1, 5]`) → emits `("test", test)`; no log.
- `lvl == reg_level` and `lvl == start_level` (window edges) → emits `("test", test)` (boundary: window is inclusive, `> / <` are strict).
- `lvl > reg_level` (e.g. `lvl=6`, `reg_level=5`) → emits `("skip", {"key": test["key"], "result": SkipResults})` and one `log.info("test_result", result="SKIP", …)`; `logging_handler.failure is False` (boundary: above the upper bound; SKIP does not drive exit).
- `lvl < start_level` (e.g. `lvl=0`, `start_level=1`) → emits `("skip", {"key": test["key"], "result": SkipResults})` and one INFO `test_result` (boundary: below the lower bound).

## Acceptance criteria

- Tests pass.
- Both output ports (`test`, `skip`) are exercised: `test` forwards the `test` edge unchanged, and the `skip` diversion path emits a `SkipResults` `result` and logs one INFO `test_result` (collected by `SummaryProcessor`, [10c](10c-summary-handler.md); no exit contribution).
- The `modules/config.yaml` manifest entry `{ name: filter-reglvl, class_name: FilterRegLvlMod }` validates and the harness resolves `filter-reglvl` → `FilterRegLvlMod`.

## Constraints

- Window test is `[start_level, reg_level]`; when both bounds are `None`, every test is kept.
- Pass only the builder **name** to `get_reglvl(builder_cfg.get_name())`; the persistent port carries the whole `RtlBuilderConfig` because the same payload feeds `cc-build`/`seed`/ `sim-build` downstream.
- SKIP is a **pass-like routing decision, not a failure** — on skip, log `test_result` at INFO (`log.info`, **never** `log.error`/`log.fatal`) and emit `("skip", {key, result: SkipResults})`. The `skip` port is unwired; the INFO `test_result` is what reaches the summary.
- Forward the test edge unchanged on the `test` port (`("test", test)`); read fields as `test["value"]` / `test["key"]` (the `{key, value}` edge shape).
- Use string-literal port names (`test`/`skip`); stay graph-agnostic.

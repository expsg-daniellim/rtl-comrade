# Spec 05e: load-model (`LoadModelMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`TestConfig`
fields `suite_dir` / `model_path` / `model_name` / `model`), spec
[01c](01c-model-schema.md) (`LoadModelMod` constructs `ModelConfigLoader`).
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

Lazily resolve and attach the test's `ModelConfig`, routing a per-test FAIL on lookup or
load failure rather than aborting the run.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   ctx
outputs:  default → ctx   (test now carries its model)
          fail    → result
```

```python
class LoadModelMod:
    def run(self, ctx):
        resolved = ctx["test"].suite_dir / ctx["test"].model_path
        try:
            model = ModelConfigLoader(str(resolved)).get_model(ctx["test"].model_name)
        except Exception as e:   # loader raises (Plan B) on I/O / parse / lookup miss
            log.error("load_model_failed", key=ctx["key"], model_path=str(resolved), err=str(e))
            return ("fail", { "key": ctx["key"], "result": ... })
        ctx["test"].model = model
        return ("default", ctx)
```

## Algorithm

1. Resolve the model file: `resolved = ctx["test"].suite_dir / ctx["test"].model_path` (fields
   per spec 01b).
2. Load it: construct `ModelConfigLoader(str(resolved))` and call
   `loader.get_model(ctx["test"].model_name)` (spec 01c).
3. Attach and pass through: `ctx["test"].model = model`; emit `("default", ctx)`.
4. **Failure — lookup/load miss.** Wrap step 2 in `try/except Exception` (Plan B's loader
   *raises* rather than `log.critical`-ing — spec 01c): file I/O, parse, schema mismatch, or
   model-not-in-file → emit `("fail", {"key": ctx["key"], "result": <FAIL with str(e) in
   desc>})` and `log.error` at emission with the resolved `model_path`. This is the Notable
   divergence from rtl_buddy: a per-test FAIL keeps the run going where rtl_buddy aborts.

## Deliverables

In `modules/rtl_test/setup.py` (continuing from spec 04):

- `LoadModelMod` — `(ctx)` → resolves `resolved = ctx["test"].suite_dir /
  ctx["test"].model_path` (fields per spec [01b](01b-suite-schema.md)), constructs
  `ModelConfigLoader(str(resolved))` (spec [01c](01c-model-schema.md)), calls
  `loader.get_model(ctx["test"].model_name)`, assigns
  `ctx["test"].model = the_model`, emits `("default", ctx)`.
  **Failure handling**: catch broad `Exception` from both `ModelConfigLoader.__init__`
  (I/O / parse / schema mismatch — Plan B's loader **raises rather than
  `log.critical`s**, see spec [01c — Notable divergences](01c-model-schema.md)) and
  `loader.get_model(name)` (model not in file). Specific classes in play:
  `FileNotFoundError`, `PermissionError`, `IsADirectoryError` (file I/O);
  `serde.SerdeError` / `yaml.YAMLError` (parse); `TypeError` / `KeyError` (schema
  mismatch); `KeyError` or custom `ModelNotFoundError` (lookup miss). Emit
  `("fail", {"key": ctx["key"], "result": <FAIL payload with `str(e)` in `desc`>})` and
  call `log.error` at emission with the resolved `model_path`. **Notable
  divergence from rtl_buddy**: per-test FAIL preserves run continuity; rtl_buddy
  aborts the whole run via `logger.critical` inside `ModelConfigLoader`
  (`rtl_buddy/src/rtl_buddy/config/model.py:78-81,100`; [07 settled
  10](../07-ambiguities-and-assumptions.md)).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/model.py:66-100` — `ModelConfigLoader.__init__` + `get_model`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: load-model, class_name: LoadModelMod }
```

## Tests

In `modules/tests/test_selection.py`:

- `load-model` attaches model from a real `models.yaml`.
- Missing model / unreadable `models.yaml` → emits `("fail", ...)` with `str(e)` in
  `desc` and `log.error` (no run abort).

## Acceptance criteria

- Tests pass.
- Both output ports (`default`, `fail`) are exercised; the fail path routes a per-test
  FAIL `result` and logs at ERROR without aborting the run.

## Constraints

- On success attach `ctx["test"].model = the_model` and emit `("default", ctx)`.
- Catch broad `Exception` from both `ModelConfigLoader(...)` construction and `get_model(...)`
  (the loader **raises** in Plan B — spec [01c](01c-model-schema.md)) → emit `("fail", {key,
  result: <FAIL with str(e)>})` on the **unwired** `fail` port and `log.error` at emission with
  the resolved `model_path`.
- **Must not** `log.critical` / abort the run — per-test FAIL preserves run continuity; this is
  the deliberate divergence from rtl_buddy.
- Use string-literal port names (`default`/`fail`).

# Spec 04e: resolve-builder (`ResolveBuilderMod`)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md)
(`RtlBuilderConfig`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

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

Pick the active `RtlBuilderConfig` from `platform_cfg`, honouring the CLI `builder`
override, and emit `builder_cfg`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   platform_cfg, builder:str = ""
outputs:  default → builder_cfg
```

```python
class ResolveBuilderMod:
    def run(self, platform_cfg, builder:str = ""):
        name = builder or platform_cfg.default_builder
        builder_cfg = platform_cfg.builders.get(name)
        if builder_cfg is None:
            log.critical("builder_not_found", builder=name)
        return ("default", builder_cfg)
```

## Algorithm

1. Pick the name: `name = builder or platform_cfg.default_builder` — the CLI override wins; an
   empty string falls back to the platform default.
2. Look it up: `builder_cfg = platform_cfg.builders.get(name)`.
3. If found, emit `("default", builder_cfg)`.
4. **Failure — unknown / none configured.** If `builder_cfg is None` (the named builder is not
   in the platform's configured list, or no builders are configured at all):
   `log.critical(f"named builder {name} not in configured builders
   {sorted(platform_cfg.builders)}")` (harness exits 1). rtl_buddy raises
   `typer.BadParameter`; Plan B uses `log.critical` for uniform exit semantics.

## Deliverables

In `modules/rtl_test/setup.py`:

- `ResolveBuilderMod` — picks the active `RtlBuilderConfig` from `platform_cfg` honouring
  the CLI `builder` override; critical-logs on unknown override; emits `builder_cfg`.
  **Failure handling**: post-lookup check — if `builder` override is non-empty and not in
  the platform's `cfg-rtl-builder` list, `log.critical(f"named builder {builder} not in
  configured builders {sorted(...)}")` (rtl_buddy's `rtl_buddy.py:76-80` raises
  `typer.BadParameter`; Plan B uses log.critical for uniform exit semantics). Empty list
  (`no builders configured`) is also `log.critical` (`root.py:151`).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/platform.py:63-84` — `PlatformConfigFile.initialise`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: resolve-builder, class_name: ResolveBuilderMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: a `platform_cfg` fixture with a
`default_builder` and a `builders` dict; `logging_handler` for the `log.critical` paths.

- `builder=""` (no override) with `default_builder` present in `builders` → emits
  `("default", builders[default_builder])` (empty string falls back to the platform default).
- `builder="<name>"` override naming a configured builder → emits
  `("default", builders["<name>"])` (override wins over the default).
- `builder="<unknown>"` not in `builders` → `builder_cfg is None` → `log.critical` →
  `pytest.raises(SystemExit)`.
- `builder=""` with an empty `builders` dict (no builders configured) → lookup yields `None`
  → `log.critical` → `pytest.raises(SystemExit)` (boundary: empty configured list).

## Acceptance criteria

- Tests pass.
- Produces the correct `builder_cfg` value (honouring the `builder` override) from a real
  rtl_buddy `root_config.yaml` fixture (contributes to the setup-only end-to-end graph —
  see [04 index](04-setup-modules.md#acceptance-criteria)).

## Constraints

- `unit` contract; emit on the string-literal `default` port.
- The CLI `builder` override wins; an empty string falls back to `platform_cfg.default_builder`.
- Unknown override or no builders configured → `log.critical` (harness exit 1). Use
  `log.critical` (not rtl_buddy's `typer.BadParameter`) so exit semantics stay uniform with the
  rest of the setup chain.

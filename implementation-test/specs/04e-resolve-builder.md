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

In `modules/tests/test_setup.py`:

- Builder resolve honours override; critical on bad name.

## Acceptance criteria

- Tests pass.
- Produces the correct `builder_cfg` value (honouring the `builder` override) from a real
  rtl_buddy `root_config.yaml` fixture (contributes to the setup-only end-to-end graph —
  see [04 index](04-setup-modules.md#acceptance-criteria)).

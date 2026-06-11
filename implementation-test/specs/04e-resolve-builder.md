# Spec 04e: resolve-builder (`ResolveBuilderMod`)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md)
(`RtlBuilderConfig`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

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

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

## Tests

In `modules/tests/test_setup.py`:

- Builder resolve honours override; critical on bad name.

## Acceptance criteria

- Tests pass.
- Produces the correct `builder_cfg` value (honouring the `builder` override) from a real
  rtl_buddy `root_config.yaml` fixture (contributes to the setup-only end-to-end graph —
  see [04 index](04-setup-modules.md#acceptance-criteria)).

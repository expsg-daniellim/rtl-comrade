# Spec 04e: resolve-builder (`ResolveBuilderMod`)

**Depends on:** spec 01 (schema), spec [01a](01a-builder-schema.md) (`RtlBuilderConfig`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index: [idx-04 — Setup modules](../idx-04-setup.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Pick the active `RtlBuilderConfig` from the root builders dict — using the platform's declared builder name, honouring the CLI `builder` override — and emit `builder_cfg`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   root_cfg, platform_cfg, builder:str = ""
outputs:  default → builder_cfg
```

```python
class ResolveBuilderMod:
    def run(self, root_cfg, platform_cfg, builder:str = ""):
        name = builder or platform_cfg.builder          # CLI override wins, else platform's declared builder name
        builder_cfg = root_cfg.rtl_builder_cfgs.get(name)
        if builder_cfg is None:
            log.fatal("builder_not_found", builder=name)
        return ("default", builder_cfg)
```

## Algorithm

1. Pick the name: `name = builder or platform_cfg.builder` — the CLI override wins; an empty string falls back to the platform's declared builder name (`PlatformConfigFile.builder`, a `str | None`).
2. Look it up in the **root** builders dict: `builder_cfg = root_cfg.rtl_builder_cfgs.get(name)`. The dict (keyed by builder name) lives on `RootConfig`, not on the platform — mirroring rtl_buddy, where `platform.initialise(builders, …)` resolves `builders[self.builder]` / `builders[builder_override]` against `RootConfig.rtl_builder_cfgs` (`root.py:94,115`, `platform.py:63-84`).
3. If found, emit `("default", builder_cfg)`.
4. **Failure — unknown / none configured.** If `builder_cfg is None` (the name is missing — an unknown override, a `None` platform builder with no override, or no builders configured at all): `log.fatal(f"named builder {name} not in configured builders {sorted(root_cfg.rtl_builder_cfgs)}")` (harness exits 1). rtl_buddy raises `typer.BadParameter`; this plan uses `log.fatal` for uniform exit semantics.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `ResolveBuilderMod` — picks the active `RtlBuilderConfig` from `root_cfg.rtl_builder_cfgs` using the platform's declared builder name (`platform_cfg.builder`), honouring the CLI `builder` override; critical-logs on unknown / unset; emits `builder_cfg`. Takes **three** inputs: `root_cfg` (the builders dict), `platform_cfg` (the declared name), and the persistent CLI `builder` override.
  **Failure handling**: post-lookup check — if the resolved `name` is not in `root_cfg.rtl_builder_cfgs` (unknown override, `None` platform builder with no override, or no builders configured), `log.fatal(f"named builder {name} not in configured builders {sorted(root_cfg.rtl_builder_cfgs)}")` (rtl_buddy's `rtl_buddy.py:76-80` raises `typer.BadParameter` for the override and `platform.py:78-79` criticals on the unset case; this plan uses `log.fatal` for uniform exit semantics). Empty builders dict is also covered (`root.py:151`).
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/platform.py:63-84` (`PlatformConfigFile.initialise`) + `config/root.py:94` (the `rtl_builder_cfgs` dict).

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: resolve-builder, class_name: ResolveBuilderMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: a `root_cfg` fixture carrying an `rtl_builder_cfgs` dict (keyed by builder name); a `platform_cfg` fixture whose `builder` names a configured builder; `logging_handler` for the `log.fatal` paths.

- `builder=""` (no override) with `platform_cfg.builder` present in `rtl_builder_cfgs` → emits `("default", rtl_builder_cfgs[platform_cfg.builder])` (empty string falls back to the platform's declared builder).
- `builder="<name>"` override naming a configured builder → emits `("default", rtl_builder_cfgs["<name>"])` (override wins over the platform default).
- `builder="<unknown>"` not in `rtl_builder_cfgs` → `builder_cfg is None` → `log.fatal` → `pytest.raises(typer.Exit)`.
- `builder=""` with `platform_cfg.builder = None` (platform declares no builder, no override) → lookup yields `None` → `log.fatal` → `pytest.raises(typer.Exit)` (boundary: unset builder).
- `builder=""` with an empty `rtl_builder_cfgs` dict (no builders configured) → lookup yields `None` → `log.fatal` → `pytest.raises(typer.Exit)` (boundary: empty configured list).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: produces the correct `builder_cfg` value (honouring the `builder` override) from a real rtl_buddy `root_config.yaml` fixture.
- Failure idiom exercised: a named builder absent from the platform → `log.fatal(f"named builder {name} not in configured builders ...")` (harness exit 1).
- The `modules/config.yaml` manifest entry `{ name: resolve-builder, class_name: ResolveBuilderMod }` validates and the harness resolves `resolve-builder` → `ResolveBuilderMod`.

## Constraints

- `unit` contract; emit on the string-literal `default` port.
- Three inputs: `root_cfg` (holds `rtl_builder_cfgs`), `platform_cfg` (holds the declared `builder` name), and the persistent CLI `builder`. The builders dict is a **root** concern — do not look for it on `platform_cfg`.
- The CLI `builder` override wins; an empty string falls back to `platform_cfg.builder`.
- Unknown override, unset platform builder, or no builders configured → `log.fatal` (harness exit 1). Use `log.fatal` (not rtl_buddy's `typer.BadParameter`) so exit semantics stay uniform with the rest of the setup chain.

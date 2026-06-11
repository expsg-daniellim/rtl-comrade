# Spec 04c: parse-root-config (`ParseRootConfigMod`)

**Depends on:** spec 01 (schema).
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

Read the discovered root-config path, deserialise it into the schema, and emit `root_cfg`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   path:Path
outputs:  default → root_cfg
```

```python
class ParseRootConfigMod:
    def run(self, path:Path):
        try:
            raw = from_yaml(RootConfigFile, path.read_text())
            return ("default", RootConfig(raw))
        except Exception as e:   # I/O, parse, schema mismatch — all unrecoverable here
            log.critical("root_config_load_failed", path=str(path), err=str(e))
```

## Deliverables

In `modules/rtl_test/setup.py`:

- `ParseRootConfigMod` — reads the path, deserialises into the schema (spec 01); emits
  `root_cfg`.
  **Failure handling**: catch broad `Exception` from the YAML load (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:88-89`). Specific classes in play:
  `FileNotFoundError`, `PermissionError`, `IsADirectoryError` (file I/O);
  `serde.SerdeError` or `yaml.YAMLError` (parse); `TypeError` / `KeyError` (schema /
  dataclass mismatch). Convert to `log.critical(f"failed to load {path}: {e}")`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:38-48` — `RootConfigFile`/`RootRtlField` serde renames; load at `root.py:84-90`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: parse-root-config, class_name: ParseRootConfigMod }
```

## Tests

In `modules/tests/test_setup.py`:

- Parse round-trips an unmodified rtl_buddy `root_config.yaml`.

## Acceptance criteria

- Tests pass.
- Produces a correct `root_cfg` value from a real rtl_buddy `root_config.yaml` fixture
  (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).

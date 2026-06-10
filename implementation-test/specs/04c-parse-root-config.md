# Spec 04c: parse-root-config (`ParseRootConfigMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Goal

Read the discovered root-config path, deserialise it into the schema, and emit `root_cfg`.

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

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

## Tests

In `modules/tests/test_setup.py`:

- Parse round-trips an unmodified rtl_buddy `root_config.yaml`.

## Acceptance criteria

- Tests pass.
- Produces a correct `root_cfg` value from a real rtl_buddy `root_config.yaml` fixture
  (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).

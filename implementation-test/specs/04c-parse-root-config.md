# Spec 04c: parse-root-config (`ParseRootConfigMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[idx-04 — Setup modules](../idx-04-setup.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain
(`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

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
            log.fatal("root_config_load_failed", path=str(path), err=str(e))
```

## Algorithm

1. Read the file: `text = path.read_text()`.
2. Deserialise into the raw schema and wrap it: `raw = from_yaml(RootConfigFile, text)`, then
   `RootConfig(raw)`.
3. Emit `("default", RootConfig(raw))`.
4. **Failure — load/parse/schema error.** Wrap steps 1–2 in `try/except Exception`: file I/O
   (`FileNotFoundError`/`PermissionError`/`IsADirectoryError`), parse
   (`serde.SerdeError`/`yaml.YAMLError`), or schema mismatch (`TypeError`/`KeyError`) are all
   unrecoverable here → `log.fatal(f"failed to load {path}: {e}")` (harness exits 1). See
   Failure handling below for the exception catalogue.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `ParseRootConfigMod` — reads the path, deserialises into `RootConfigFile`, then wraps it as
  `RootConfig(raw)` (the thin runtime wrapper that precomputes `rtl_builder_cfgs`, per
  [spec 01 — `root.py` schema](01-shared-schema.md#rootpy-schema-detailed)); emits `root_cfg`.
  **Failure handling**: catch broad `Exception` from the YAML load (mirrors
  `rtl_buddy/src/rtl_buddy/config/root.py:88-89`). Specific classes in play:
  `FileNotFoundError`, `PermissionError`, `IsADirectoryError` (file I/O);
  `serde.SerdeError` or `yaml.YAMLError` (parse); `TypeError` / `KeyError` (schema /
  dataclass mismatch). Convert to `log.fatal(f"failed to load {path}: {e}")`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:38-48` — `RootConfigFile`/`RootRtlField` serde renames; load at `root.py:84-90`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: parse-root-config, class_name: ParseRootConfigMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: a committed rtl_buddy `root_config.yaml`
fixture for the happy path; `tmp_path` files for the malformed cases; `logging_handler` for
the `log.fatal` paths.

- A valid `root_config.yaml` path → emits `("default", RootConfig)`; every field round-trips
  equal to the equivalent rtl_buddy `RootConfig` over the same YAML.
- Path to a nonexistent file → `FileNotFoundError` caught → `log.fatal` →
  `pytest.raises(SystemExit)`.
- Path to a malformed-YAML file (`tmp_path` with unparseable text) → `yaml.YAMLError` caught
  → `log.fatal` → `pytest.raises(SystemExit)`.
- Path to schema-mismatched YAML (required field missing / wrong type) → `TypeError`/`KeyError`
  caught → `log.fatal` → `pytest.raises(SystemExit)`.
- Path to a directory rather than a file → `IsADirectoryError` caught → `log.fatal` →
  `pytest.raises(SystemExit)` (boundary: I/O-class error).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: produces a correct `root_cfg` value from a real rtl_buddy
  `root_config.yaml` fixture (the reference suite `../rtl-buddy-proj-template/design/sandbox`,
  per `rtl_buddy/AGENTS.md`).
- Failure idiom exercised: an unreadable / unparseable / schema-mismatched config →
  `log.fatal(f"failed to load {path}: {e}")` (harness exit 1).
- The `modules/config.yaml` manifest entry `{ name: parse-root-config, class_name: ParseRootConfigMod }`
  validates and the harness resolves `parse-root-config` → `ParseRootConfigMod`.

## Constraints

- `unit` contract; emit on the string-literal `default` port.
- Catch broad `Exception` around the read + deserialise (file I/O, `serde.SerdeError`/
  `yaml.YAMLError` parse, `TypeError`/`KeyError` schema mismatch) and convert to
  `log.fatal` (harness exit 1) — a setup-domain config error, never a port-routed result.
- Do **not** demote the failure to `log.error`: a malformed root config is unrecoverable.

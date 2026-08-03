# Spec 04c: parse-root-config (`ParseRootConfigMod`)

**Depends on:** spec 01 (schema — `RootConfig` holder + the nested `RootRtlField`/`PlatformConfig`), spec [01a](01a-builder-schema.md) (`RtlBuilderConfig`, nested in `RootConfigFile.builders`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index: [idx-04 — Setup modules](../idx-04-setup.md).

This module **owns the raw `RootConfigFile` serde container** (table below): it is read once by `from_yaml` and immediately unwrapped into the runtime `RootConfig`, so it never rides a graph edge and lives here with its sole consumer rather than in the schema package (the schema package holds only edge-borne types — see [idx-01](../idx-01-schema.md)).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Read the discovered root-config path, deserialise it into the schema, and emit `root_cfg`.

## Raw schema (`RootConfigFile`) — owned here

The top-level `@serde` container read straight from `root_config.yaml`. Faithful port of rtl_buddy's `config/root.py:42-48` (minus the dropped `veribles` field). It nests `RootRtlField` and `PlatformConfig` (both owned by [spec 01](01-shared-schema.md#rootpy-schema-detailed)) and `RtlBuilderConfig` ([01a](01a-builder-schema.md)). Defined as a module-private dataclass in `setup.py` — not re-exported from the schema package.

| field         | type                          | YAML rename          | default               | notes                                                                 |
|---------------|-------------------------------|----------------------|-----------------------|-----------------------------------------------------------------------|
| `filetype`    | `Literal['project_root_config']` | `rtl-buddy-filetype` | required           | Tag literal.                                                          |
| `cfg_rtl_reg` | `RootRtlField`                | `cfg-rtl-reg`        | required              | Reg-path holder (passed through to `RootConfig.cfg_rtl_reg`).         |
| `builders`    | `list[RtlBuilderConfig]`      | `cfg-rtl-builder`    | required              | Builder list ([01a](01a-builder-schema.md)); collapsed into `RootConfig.rtl_builder_cfgs`. |
| `platforms`   | `list[PlatformConfig]`    | `cfg-platforms`      | required              | Platform list (passed through to `RootConfig.platforms`).             |

The root `cfg-verible` key is **not** a field — left unparsed (pyserde ignores it). Preserve the `field(rename=...)` targets exactly (keep hyphens); do **not** Pythonify.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

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
            root_cfg = RootConfig(platforms=raw.platforms, rtl_builder_cfgs={c.get_name(): c for c in raw.builders}, cfg_rtl_reg=raw.cfg_rtl_reg)   # rtl_builder_cfgs precompute mirrors root.py:94
            return ("default", root_cfg)
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError, OSError) as e:   # file I/O — unrecoverable
            log.fatal("root_config_load_failed", path=str(path), exc_info=e)
        except (SerdeError, MarkedYAMLError, ReaderError) as e:   # parse — unrecoverable
            log.fatal("root_config_load_failed", path=str(path), exc_info=e)
```

The caught-type set is brought to parity with the harness's own config-load ladder (`loader_utils.load_config_file`, `src/rtl_comrade/loader_utils.py:38-61`): file I/O `UnicodeDecodeError`/`FileNotFoundError`/`IsADirectoryError`/`PermissionError`/`OSError`, parse `SerdeError`/`MarkedYAMLError`/`ReaderError`. The two existing grouped clauses and the single `root_config_load_failed` event are kept — the harness splits the ladder per-type only to attach category-specific log fields, which this module does not need. The earlier `(serde.SerdeError, yaml.YAMLError)` and `(TypeError, KeyError)` clauses are replaced: pyserde wraps missing-field / wrong-type / `rtl-buddy-filetype` discriminator mismatch in `SerdeError` (so `TypeError`/`KeyError` never actually caught them), and `yaml.YAMLError` is narrowed to the two subclasses the harness names (`MarkedYAMLError` for positioned syntax errors, `ReaderError` for reader/encoding errors). Imports: `SerdeError` from `serde`, `from_yaml` from `serde.yaml`, `MarkedYAMLError` from `yaml.error`, `ReaderError` from `yaml.reader` — shared with the setup chain ([§ Before you start](#before-you-start)).

## Algorithm

1. Read the file: `text = path.read_text()`.
2. Deserialise into the raw container: `raw = from_yaml(RootConfigFile, text)`.
3. Build the runtime holder, performing the one transform (precompute the builders dict, mirrors `root.py:94`): `RootConfig(platforms=raw.platforms, rtl_builder_cfgs={c.get_name(): c for c in raw.builders}, cfg_rtl_reg=raw.cfg_rtl_reg)`. `RootConfig` is the plain `@dataclass` holder from [spec 01](01-shared-schema.md#rootpy-schema-detailed) — it takes the derived members, not the raw container.
4. Emit `("default", root_cfg)`.
5. **Failure — load/parse error.** Wrap steps 1–3 in `try` with one `except` clause per error category — file I/O (`except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError, OSError)`) and parse (`except (SerdeError, MarkedYAMLError, ReaderError)`) — each unrecoverable here → `log.fatal(f"failed to load {path}: {e}")` (harness exits 1). Catch only these named classes, not a blanket `Exception`, so an unexpected error propagates rather than being silently demoted to a config-load failure. See Failure handling below for the exception catalogue.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- The module-private `RootConfigFile` raw `@serde` container (table in [§ Raw schema](#raw-schema-rootconfigfile--owned-here) above) — defined in `setup.py`, not exported from the schema package.
- `ParseRootConfigMod` — reads the path, deserialises into `RootConfigFile`, then derives the runtime `RootConfig` holder from its members (precomputing `rtl_builder_cfgs = {c.get_name(): c for c in raw.builders}`, per [spec 01 — `root.py` schema](01-shared-schema.md#rootpy-schema-detailed)); emits `root_cfg`.
  **Failure handling**: catch the load/parse classes on a per-category basis (rtl_buddy uses a blanket `except Exception` at `root.py:88-89`; here we enumerate the classes instead so an unexpected error is not swallowed). Two `except` clauses: `(UnicodeDecodeError, FileNotFoundError, IsADirectoryError, PermissionError, OSError)` (file I/O); `(SerdeError, MarkedYAMLError, ReaderError)` (parse). The caught-type set matches the harness's own `loader_utils.load_config_file` ladder (`src/rtl_comrade/loader_utils.py:38-61`); pyserde wraps schema / `rtl-buddy-filetype` discriminator / type mismatch in `SerdeError`, so the former `(TypeError, KeyError)` clause is dropped (it never caught them) and `yaml.YAMLError` is narrowed to `MarkedYAMLError`/`ReaderError`. Each converts to `log.fatal(f"failed to load {path}: {e}")`.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/root.py:38-48` — `RootConfigFile`/`RootRtlField` serde renames; load at `root.py:84-90`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: parse-root-config, class_name: ParseRootConfigMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: a committed rtl_buddy `root_config.yaml` fixture for the happy path; `tmp_path` files for the malformed cases; `logging_handler` for the `log.fatal` paths.

- A valid `root_config.yaml` path → emits `("default", RootConfig)`; every field round-trips equal to the equivalent rtl_buddy `RootConfig` over the same YAML. `rtl_builder_cfgs` contains every `cfg-rtl-builder` entry keyed by `get_name()`.
- A `root_config.yaml` carrying `cfg-verible` (root) and per-platform `verible` keys loads (those keys ignored) without error and produces a field-equivalent `RootConfig` (drop-in compatibility; moved here from spec 01 with the `from_yaml` call).
- Path to a nonexistent file → `FileNotFoundError` caught → `log.fatal` → `pytest.raises(typer.Exit)`.
- Path to a directory rather than a file → `IsADirectoryError` caught → `log.fatal` → `pytest.raises(typer.Exit)` (boundary: I/O-class error).
- Path to a non-UTF-8 file → `UnicodeDecodeError` caught → `log.fatal` → `pytest.raises(typer.Exit)`.
- Path to a malformed-YAML file (`tmp_path` with unparseable text) → `MarkedYAMLError` caught → `log.fatal` → `pytest.raises(typer.Exit)`.
- Path to schema-mismatched YAML (required field missing / wrong type / bad `rtl-buddy-filetype` discriminator) → `SerdeError` caught (pyserde wraps the underlying `TypeError`/`KeyError`) → `log.fatal` → `pytest.raises(typer.Exit)`.

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: produces a correct `root_cfg` value from a real rtl_buddy `root_config.yaml` fixture (`../rtl-buddy-proj-template/root_config.yaml`, per `rtl_buddy/AGENTS.md`).
- Failure idiom exercised: an unreadable / unparseable / schema-mismatched config → `log.fatal(f"failed to load {path}: {e}")` (harness exit 1).
- The `modules/config.yaml` manifest entry `{ name: parse-root-config, class_name: ParseRootConfigMod }` validates and the harness resolves `parse-root-config` → `ParseRootConfigMod`.

## Constraints

- `unit` contract; emit on the string-literal `default` port.
- Catch the read + deserialise failures per category — file I/O (`UnicodeDecodeError`/`FileNotFoundError`/`IsADirectoryError`/`PermissionError`/`OSError`), parse (`SerdeError`/`MarkedYAMLError`/`ReaderError`) — in separate `except` clauses, not one blanket `Exception`, and convert each to `log.fatal` (harness exit 1) — a setup-domain config error, never a port-routed result.
- Do **not** demote the failure to `log.error`: a malformed root config is unrecoverable.

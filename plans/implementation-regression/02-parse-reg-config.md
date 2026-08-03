# Spec 02: parse-reg-config (`ParseRegConfigMod`)

**Depends on:** nothing — the module is self-contained.
**References:** [00-overview](00-overview.md); `rtl_buddy/src/rtl_buddy/config/reg.py:12-21` — `RegConfigFile` serde type; `rtl_buddy/src/rtl_buddy/config/reg.py:23-50` — `RegConfig.__init__` loading and suite-config resolution.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms, generator convention).

## Goal

Deserialise `regressions.yaml` and yield one resolved `Path` per `test-configs` entry. This is the fan-out point: one reg config in, N suite config paths out.

## Surface

```
contract:          unit (fan-out: yields N suite paths from one input)
inputs:            reg_config_path:Path
outputs:           default → Path (generator: 1 → N)
```

```python
@serde
class RegConfigFile:
    filetype:Literal['reg_config'] = field(rename='rtl-buddy-filetype')
    test_configs:list[str] = field(rename='test-configs', default_factory=list)


class ParseRegConfigMod:
    def run(self, reg_config_path:Path):
        try:
            raw = from_yaml(RegConfigFile, reg_config_path.read_text(encoding="utf-8"))
        except FileNotFoundError as e:
            log.fatal("reg_config_not_found", path=str(reg_config_path), exc_info=e)
        except SerdeError as e:
            log.fatal("reg_config_serde_error", path=str(reg_config_path), message=str(e), exc_info=e)
        except MarkedYAMLError as e:
            log.fatal("reg_config_yaml_invalid", path=str(reg_config_path), problem=e.problem, exc_info=e)
        for entry in raw.test_configs:
            yield ("default", (reg_config_path.parent / entry).resolve())
```

The `RegConfigFile` mirrors the upstream serde type, preserving the YAML field names exactly. Each yielded `Path` is resolved against the reg config's directory — `parse-suite-config` downstream receives it as its `test_config:str` input and resolves it (idempotent on an absolute path).

## Algorithm

1. Read `reg_config_path` as UTF-8 text.
2. Deserialise via `from_yaml(RegConfigFile, ...)`.
3. On `FileNotFoundError` → `log.fatal("reg_config_not_found")`.
4. On `SerdeError` → `log.fatal("reg_config_serde_error")`.
5. On `MarkedYAMLError` → `log.fatal("reg_config_yaml_invalid")`.
6. For each entry in `test_configs`, yield `("default", (reg_config_path.parent / entry).resolve())`.

## `RegConfigFile` serde container

Module-private — read-once, never rides a graph edge. Same convention as `SuiteConfigFile` in `ParseSuiteConfigMod`.

```python
@serde
class RegConfigFile:
    filetype:Literal['reg_config'] = field(rename='rtl-buddy-filetype')
    test_configs:list[str] = field(rename='test-configs', default_factory=list)
```

## Deliverables

- `ParseRegConfigMod` (and `RegConfigFile`) in `modules/rtl_buddy/setup.py`.
- **Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`:
  ```yaml
    - { name: parse-reg-config, class_name: ParseRegConfigMod }
  ```

## Tests

In `modules/tests/test_setup.py`.

- Valid `regressions.yaml` with two `test-configs` entries → yields two `("default", Path)` values, each resolved against the reg config's directory.
- Valid `regressions.yaml` with an empty `test-configs` list → yields nothing (generator exhausts immediately).
- Missing file → `log.fatal("reg_config_not_found")`.
- Malformed YAML → `log.fatal("reg_config_yaml_invalid")`.
- Valid YAML, schema mismatch → `log.fatal("reg_config_serde_error")`.

## Acceptance criteria

- All five test cases pass.
- `parse-reg-config` → `ParseRegConfigMod` resolves in the manifest.
- Each yielded path is resolved against the reg config's parent directory, not CWD.
- Error paths abort via `log.fatal` with distinct event names.

## Docs

Add a `docs/modules/parse-reg-config.md` page and update `docs/modules/index.md` to include it. Follow `docs/creating-documentation.md` and `docs/modules/doc-structure.md`.

## Constraints

- **No graph knowledge.** The module does not know about `parse-suite-config` or the graph; it parses one file and yields paths.
- **Contract: `unit`.** The single input arrives once from `resolve-reg-config-path`. The generator yields N outputs from that one invocation.
- **`RegConfigFile` is module-private.** It does not appear on any graph edge.

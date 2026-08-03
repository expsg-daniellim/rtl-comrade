# Spec 05e: load-model (`LoadModelMod`)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`TestConfig` fields `suite_dir` / `model_path` / `model`), spec [01c](01c-model-schema.md) (the frozen runtime `ModelConfig` this module constructs and emits).
**References:** [03 — Selection/expansion section](../03-module-catalog.md). Parent index: [idx-05 — Selection and expansion modules](../idx-05-selection-expansion.md).

This module **owns the raw `ModelConfigFile`/`ModelConfigFileItem` serde shapes (pure data shapes) and the raw→runtime conversion** (tables below): they are read once by `from_yaml` and immediately converted into the runtime `ModelConfig`, so they never ride a graph edge and live here with their sole consumer rather than in the schema package ([idx-01](../idx-01-schema.md)). The read + lookup + construct happens inline in `run`, **not** as a method on the raw type or a separate loader class (unlike rtl_buddy's `ModelConfigLoader`). Spec [01c](01c-model-schema.md) defines the runtime shape they produce.

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Lazily resolve the test's `ModelConfig` and emit it on its own `model` edge (not attached to `TestConfig`), routing a per-test FAIL on lookup or load failure rather than aborting the run.

## Raw schema & conversion (owned here)

`ModelConfigFile` and `ModelConfigFileItem` are module-private types in `setup.py` — **not** re-exported from the schema package (neither rides an edge). They are the read shape from which `run` constructs the runtime `ModelConfig` owned by spec [01c](01c-model-schema.md). rtl_buddy made `ModelConfig` *itself* the list-element serde type (`model.py:53-63`) and stamped `path` onto it later; this plan splits raw from runtime — `ModelConfigFileItem` is the YAML-faithful per-entry read shape, and the frozen runtime `ModelConfig` is **constructed** from it (the same raw→runtime split `TestConfigFile`→`TestConfig` uses).

### `ModelConfigFile` (raw)

| field                | type                          | YAML rename          | default                       | notes                                                                                  |
|----------------------|-------------------------------|----------------------|-------------------------------|----------------------------------------------------------------------------------------|
| `rtl_buddy_filetype` | `Literal['model_config']`     | `rtl-buddy-filetype` | required                      | Discriminator; serde raises on mismatch (caught by `LoadModelMod`'s `model_parse_error` clause → per-test FAIL). |
| `models`             | `list[ModelConfigFileItem]`   | (none)               | `field(default_factory=list)` | Empty `models:` is legal and produces a no-op file (no models retrievable).            |

Preserve the `rtl-buddy-filetype` rename (keep the hyphen); do **not** Pythonify. Source: `model.py:53-63`.

### `ModelConfigFileItem` (raw)

One per element in `models.yaml`'s `models:` list — the YAML shape only, **no** `path` (`path` is runtime provenance supplied by `run`, never read from YAML — `model.py:97` sets it from the loader's file arg, never from the entry).

| field      | type        | YAML rename | default  | notes                                                                |
|------------|-------------|-------------|----------|----------------------------------------------------------------------|
| `name`     | `str`       | (none)      | required | Unique model identifier inside the file. Matched against the test's `model` (name). |
| `filelist` | `list[str]` | (none)      | required | Paths (relative to the `models.yaml` dir) for the model's HDL filelist. |

Source: `model.py:19-20` (the `name`/`filelist` fields of rtl_buddy's `ModelConfig`; `path` at `:21` is dropped from the read shape).

Read + lookup + construct — unrolled into `run`, **not** as a separate `ModelConfigLoader` class. rtl_buddy's loader did two things; here they are three steps, all in `LoadModelMod.run`:

1. **Read once.** Open `resolved` and `from_yaml(ModelConfigFile, ...)`. Any exception **propagates** to `run`'s `try/except` (this plan does **not** `log.fatal` here). Each class is caught in **its own `except` clause** with **its own event name** (matching `io.py`'s per-exception ladder, and the harness's config-load ladder — `loader_utils.load_config_file`, `src/rtl_comrade/loader_utils.py:38-61`): `FileNotFoundError`→`model_file_not_found`, `IsADirectoryError`→`model_is_directory`, `PermissionError`→`model_permission_denied`, `UnicodeDecodeError`→`model_invalid_unicode`, `OSError`→`model_read_error` (file I/O / decode); `SerdeError`/`MarkedYAMLError`/`ReaderError`→`model_parse_error` (parse — pyserde wraps missing-field / wrong-type / discriminator mismatch in `SerdeError`, so it surfaces there, not as raw `TypeError`/`KeyError`). Mirrors `model.py:76-81` minus its `logger.critical`.
2. **Look up by name.** Find the `ModelConfigFileItem` in `file.models` whose `name == test.model`; a miss **raises** (caught → per-test FAIL), **not** `log.fatal`. Mirrors `model.py:95-100` minus its `logger.critical`.
3. **Construct.** Build the frozen runtime `ModelConfig(name=item.name, filelist=item.filelist, path=str(resolved))` — `path` is set at construction from the resolved file path, **not** stamped onto a deserialized object (no in-place mutation, no `replace`). `write-filelist` (spec [06b](06b-write-filelist.md)) relies on `model.path` to resolve `filelist` entries relative to the `models.yaml`'s directory.

This is done in `run`, **not** as a method on the raw type and **not** factored into a single-use loader class — rtl_buddy hangs the equivalent off `ModelConfigLoader` only because it has no node to own the transform; this plan does, so the transform belongs to the node. Two divergences from rtl_buddy. (1) rtl_buddy's `ModelConfigLoader.__init__` and `get_model` call `logger.critical(...)` directly — aborting the whole run on any per-test `models.yaml` issue. Unrolled here, `run` lets read/parse/lookup errors raise and catches them to emit a per-test `fail` `result` ([07 settled 10](../07-ambiguities-and-assumptions.md)). Do **not** collapse it back to `log.fatal`. (2) `path` is dropped from the read shape and set at construction, so the runtime `ModelConfig` is a clean frozen value object rather than rtl_buddy's deserialize-then-mutate record (`model.py:21,97`). Source: `model.py:53-100`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: default
inputs:   test
outputs:  test  → TestConfig (self-keyed)   (forwarded unchanged — TestConfig is not mutated)
          model → {key, value}   (KeyedValue[ModelConfig], keyed by the test's key, joined at write-filelist)
          fail  → TestResult (self-keyed)
```

```python
class LoadModelMod:
    def run(self, test:TestConfig):               # test is the bare self-keyed TestConfig
        resolved = test.suite_dir / test.model_path
        try:
            with open(resolved) as f:
                file = from_yaml(ModelConfigFile, f.read())                            # read once (raw container)
            item = next((m for m in file.models if m.name == test.model), None)
            if item is None:
                raise LookupError(f"model {test.model!r} not in {resolved}")
            model = ModelConfig(name=item.name, filelist=item.filelist, path=str(resolved))   # frozen value, path set at construction
            yield ("test", test)                                          # forward unchanged
            yield ("model", KeyedValue(test.key, model))       # resolved model on its own edge, keyed by the test's key
        # one except per failure class — each logs its OWN event with exception-specific fields (mirrors io.py), then emits the per-test fail.
        # FileNotFound/IsADirectory/Permission precede OSError (subclasses); the log omits result/desc (they ride the emitted TestResult).
        except FileNotFoundError:
            log.error("model_file_not_found", key=test.key, test_name=test.get_name(), model_path=str(resolved))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"models.yaml not found: {resolved}"))
        except IsADirectoryError:
            log.error("model_is_directory", key=test.key, test_name=test.get_name(), model_path=str(resolved))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"{resolved} is a directory"))
        except PermissionError as e:
            log.error("model_permission_denied", key=test.key, test_name=test.get_name(), model_path=str(resolved), err=e.strerror)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read {resolved}"))
        except UnicodeDecodeError as e:
            log.error("model_invalid_unicode", key=test.key, test_name=test.get_name(), model_path=str(resolved), reason=e.reason)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"{resolved} is not valid UTF-8"))
        except (SerdeError, MarkedYAMLError, ReaderError) as e:
            log.error("model_parse_error", key=test.key, test_name=test.get_name(), model_path=str(resolved), err=str(e))
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"malformed {resolved}: {e}"))
        except LookupError:
            log.error("model_not_found", key=test.key, test_name=test.get_name(), model_path=str(resolved), model=test.model)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"model {test.model!r} not in {resolved}"))
        except OSError as e:
            log.error("model_read_error", key=test.key, test_name=test.get_name(), model_path=str(resolved), err=e.strerror, errno=e.errno)
            yield ("fail", TestResult.prep(test.key, test.get_name(), f"cannot read {resolved}"))
```

## Algorithm

1. Resolve the model file: `resolved = test.suite_dir / test.model_path` (`test` is the bare `TestConfig`; fields per spec 01b).
2. **Read once.** Open `resolved` and `file = from_yaml(ModelConfigFile, ...)` ([§ Raw schema](#raw-schema--conversion-owned-here)).
3. **Look up.** Find the `ModelConfigFileItem` in `file.models` with `name == test.model`; a miss **raises** (`LookupError`).
4. **Construct.** `model = ModelConfig(name=item.name, filelist=item.filelist, path=str(resolved))` — frozen value, `path` set at construction (no mutation, no `replace`).
5. Emit two edges in lockstep on success: `("test", test)` (forwarded unchanged — **no mutation of `TestConfig`**) and `("model", KeyedValue(test.key, model))`. They share the test's key. `load-model` sits **after `filter` but before the `sweep`/`preproc` hooks** (graph [06](../06-graph-yaml.md)): the resolved `ModelConfig` must exist when those hooks run so each can expose it to its script as `test_cfg.model` (rtl_buddy resolves the model at suite-load, before the hooks). The `model` edge then rides alongside `test` — `keyed_join`ed at every node it passes (`sweep`, `preproc`, `gate-pre`), re-keyed `#i` across the sweep fan-out — to its final consumer `write-filelist` (spec [06b](06b-write-filelist.md)), which `keyed_join`s `test`+`model` 1:1.
6. **Failure — read / parse / lookup miss.** Wrap steps 2–5 in a `try`, then catch **each failure class in its own `except` clause** — each logging its **own** event with the **exception-specific** fields (mirroring `io.py`) and emitting the per-test fail (this plan *raises* rather than `log.fatal`-ing — see below): `model_file_not_found` / `model_is_directory` / `model_permission_denied` / `model_invalid_unicode` / `model_read_error` (I/O — `model_read_error` carries `err=e.strerror`/`errno=e.errno`, `model_invalid_unicode` carries `reason=e.reason`), `model_parse_error` (parse/schema, `err=str(e)`), `model_not_found` (model-not-in-file `LookupError`, `model=test.model`). Each clause emits `("fail", TestResult.prep(test.key, test.get_name(), desc))` with a per-case human `desc` (and **neither** `test` nor `model`, so the pair drops together). The `log.error` carries `model_path` + the exception-specific fields — **not** `result`/`desc` (the `TestResult` → `results-summary`, spec [10d](10d-summarise-results.md)); the per-exception `log.error` drives the exit. This is the Notable divergence from rtl_buddy: a per-test FAIL keeps the run going where rtl_buddy aborts.

## Deliverables

In `modules/rtl_buddy/setup.py` (continuing from spec 04):

- The module-private raw `ModelConfigFileItem` and `ModelConfigFile` serde types ([§ Raw schema](#raw-schema--conversion-owned-here) above) — defined in `setup.py`, not exported from the schema package.
- `LoadModelMod` — `(test)` (`test` is the bare self-keyed `TestConfig`) resolves `resolved = test.suite_dir / test.model_path` (fields per spec [01b](01b-suite-schema.md)), reads `file = from_yaml(ModelConfigFile, ...)` from `resolved`, and finds the `ModelConfigFileItem` in `file.models` whose `name == test.model`.
  - **Construct.** Build `ModelConfig(name=item.name, filelist=item.filelist, path=str(resolved))` (frozen value, `path` set at construction — **no** mutation, **no** `replace`).
  - **Emit on success.** `("test", test)` (forwarded unchanged) **and** `("model", KeyedValue(test.key, the_model))` in lockstep via the generator. **Does not mutate `TestConfig`** — the resolved `ModelConfig` rides its own keyed edge, `keyed_join`ed at `write-filelist` (spec [06b](06b-write-filelist.md)).
  - **Failure handling.** Catch **each failure class in its own `except` clause** around the read (`from_yaml` — I/O / parse / schema mismatch) and the name lookup (model not in file → the explicit `raise`); this plan **raises rather than `log.fatal`s** ([§ Raw schema](#raw-schema--conversion-owned-here)).
  - **Classes in play, each its own event** (matching the harness's `loader_utils.load_config_file` ladder, `src/rtl_comrade/loader_utils.py:38-61`, and `io.py`'s per-exception shape): `FileNotFoundError`→`model_file_not_found`, `IsADirectoryError`→`model_is_directory`, `PermissionError`→`model_permission_denied`, `UnicodeDecodeError`→`model_invalid_unicode`, `OSError`→`model_read_error` (file I/O / decode; `OSError` **last**, since the others are its subclasses); `SerdeError`/`MarkedYAMLError`/`ReaderError`→`model_parse_error` (parse — pyserde wraps schema / discriminator / type mismatch in `SerdeError`); `LookupError`→`model_not_found` (lookup miss).
  - **Fail emission.** Each `except` clause logs its event with the **exception-specific** fields (`model_path`; plus `err=e.strerror`/`errno=e.errno` for `OSError`, `reason=e.reason` for `UnicodeDecodeError`, `err=str(e)` for parse, `model=test.model` for the lookup miss) — **not** `result`/`desc` — then emits `("fail", TestResult.prep(test.key, test.get_name(), desc))` with a per-case human `desc`. The per-exception `log.error` drives the exit; the emitted `TestResult` → `results-summary` (spec [10d](10d-summarise-results.md)).
  - **Notable divergence from rtl_buddy.** Per-test FAIL preserves run continuity; rtl_buddy aborts the whole run via `logger.critical` inside `ModelConfigLoader` (`rtl_buddy/src/rtl_buddy/config/model.py:78-81,100`; [07 settled 10](../07-ambiguities-and-assumptions.md)).
  - **Compatibility source:** `rtl_buddy/src/rtl_buddy/config/model.py:53-100` — `ModelConfigFile`/`ModelConfigLoader`, with `path` moved off the read shape and the read/lookup/construct unrolled into `run`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: load-model, class_name: LoadModelMod }
```

## Tests

In `modules/tests/test_selection.py`. Fixtures: a committed `models.yaml` fixture + a bare `test` (`TestConfig`) whose `suite_dir`/`model_path`/`model` point at it; `tmp_path` crafted files for the failure cases; `logging_handler` to assert `failure is True` **without** `typer.Exit`.

- `test` whose `model` exists in a real `models.yaml` → emits `("test", test)` (forwarded; `test.model` still holds the **name string**, unchanged — not overwritten with the resolved `ModelConfig`) **and** `("model", KeyedValue(test.key, <ModelConfig>))` keyed by the test's key; assert the emitted `model.value.name`/`model.value.filelist` equal the matched entry and `model.value.path == str(resolved)` (set at construction).
- **Read shape carries no `path` (raw/runtime split unrolled here).** `from_yaml(ModelConfigFile, ...)` over a real `models.yaml` yields `ModelConfigFileItem`s with `name`/`filelist` and **no** `path` attribute; the emitted runtime `ModelConfig` is freshly constructed (frozen) with `path == str(resolved)`. A `models.yaml` that happens to include a `path:` key is ignored by the read shape (not a field).
Failure cases — each routes to the per-test `fail` port; assert `logging_handler.failure is True` and that **no** `log.fatal`/`typer.Exit` fires (the deliberate divergence from rtl_buddy's abort — run continues):

- `test` whose `model` is absent from the file → the name lookup `raise`s `LookupError` → `log.error("model_not_found", model=test.model, …)`, emits `("fail", TestResult.prep(key, test_name, …))` and **neither `test` nor `model`**, `logging_handler.failure is True`, no `typer.Exit` (run continues).
- `test` whose resolved `model_path` does not exist → `open(resolved)` raises `FileNotFoundError` → `log.error("model_file_not_found", …)`, emits `("fail", …)`, no abort.
- `test` pointing at a malformed `models.yaml` → parse raises → `log.error("model_parse_error", err=…, …)`, emits `("fail", …)`, no abort (boundary: **each class logs its own event** — `model_file_not_found` vs `model_parse_error` vs `model_not_found` — all routing to the same `fail` port).
- `test` against a `models: []` file → the lookup finds nothing → `log.error("model_not_found", …)`, `("fail", …)`, no abort.

## Acceptance criteria

- Tests pass.
- All three output ports (`test`, `model`, `fail`) are exercised: on success `test` forwards the test edge unchanged and `model` emits the resolved `ModelConfig` on its own keyed edge; the `fail` path routes a per-test FAIL `result` and logs at ERROR without aborting the run.
- The `modules/config.yaml` manifest entry `{ name: load-model, class_name: LoadModelMod }` validates and the harness resolves `load-model` → `LoadModelMod`.

## Constraints

- The raw `ModelConfigFileItem` and `ModelConfigFile` are module-private (`setup.py`) and **not** added to the schema package's `__init__.py`. Preserve the `rtl-buddy-filetype` rename (keep the hyphen). There is **no** `ModelConfigLoader` — rtl_buddy's loader is unrolled into `run`. `ModelConfigFileItem` carries **no** `path` (it is not a YAML field; `path` is runtime provenance).
- The read + name-lookup in `run` must **raise** on I/O / parse / schema error and on a missing model — **not** `log.fatal` (the deliberate divergence). The runtime `ModelConfig` must be **constructed** with `path=str(resolved)` (`ModelConfig` is frozen, spec [01c](01c-model-schema.md)) — **not** stamped onto a deserialized object (no `replace`, no in-place `model.path = …`).
- On success emit `("test", test)` (forwarded unchanged) and `("model", KeyedValue(test.key, the_model))` in lockstep — **do not mutate `TestConfig`** (no `test.model = the_model`; `test.model` stays the name string, the resolved object rides the edge — rtl_buddy overwrites the field in place, this plan does not). The two edges share the test key so `write-filelist` `keyed_join`s them.
- Catch **each failure class in its own `except` clause** (not one `except Exception`) around the `from_yaml` read and the name lookup (both can raise in this plan — see [§ Raw schema](#raw-schema--conversion-owned-here)); each logs its own event (`model_file_not_found`/`model_is_directory`/`model_permission_denied`/`model_invalid_unicode`/`model_read_error`/`model_parse_error`/`model_not_found`) with the **exception-specific** fields (`model_path`, and `err`/`errno`/`reason`/`model` as relevant) — **not** `result`/`desc` — then emits `("fail", TestResult.prep(test.key, test.get_name(), desc))` on the `fail` port (→ `results-summary`) (and neither `test` nor `model`, dropping the pair). The per-exception `log.error` drives the exit. Order the clauses so `FileNotFoundError`/`IsADirectoryError`/`PermissionError` precede `OSError`.
- **Must not** `log.fatal` / abort the run — per-test FAIL preserves run continuity; this is the deliberate divergence from rtl_buddy.
- Use string-literal port names (`test`/`model`/`fail`); read `TestConfig` fields directly on `test` (e.g. `test.suite_dir`, `test.model`, `test.key`). The `model` edge is a `KeyedValue` (`model.value` / `model.key`).

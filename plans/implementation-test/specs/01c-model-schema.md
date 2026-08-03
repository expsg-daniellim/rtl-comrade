# Spec 01c: Model schema (`models.yaml`)

**Depends on:** none. Can run in parallel with specs 01, 01a, 01b. Adds **no** entries to the package `__init__.py` — spec 01 owns the sole re-export surface — so it never edits a file another spec touches.
**References:** [idx-01](../idx-01-schema.md) (umbrella), [01b](01b-suite-schema.md) (`TestConfig` carries `model`/`model_path`/`suite_dir`; the resolved `ModelConfig` rides a separate edge), [07 settled 1, 8](../07-ambiguities-and-assumptions.md).
**Source:** `rtl_buddy/src/rtl_buddy/config/model.py:9-51` (`ModelConfig`; the raw `ModelConfigFileItem`/`ModelConfigFile` read shape and the read/lookup at `:53-100` are owned by spec [05e](05e-load-model.md)).

## Before you start

`ModelConfig` here is a **constructed runtime value object** — a plain `frozen=True` `@dataclass`, not a `@serde` deserialization target (the same raw→runtime split as `TestConfigFile`→`TestConfig`, spec [01b](01b-suite-schema.md)). The YAML is read into the raw `@serde` `ModelConfigFileItem` (owned by `load-model`, spec [05e](05e-load-model.md)); `load-model` then **constructs** this `ModelConfig` from the matched item. It is a faithful port of rtl_buddy's `ModelConfig` *fields/methods*, so the authoritative reference is the rtl_buddy `config/*.py` source this spec cites (anchored to `v1.4.0`, commit `a69d962`); [`02 — payload conventions`](../02-payload-conventions.md) holds the frozen-payload convention it follows. All four schema specs (`01`, `01a`, `01b`, `01c`) build into the shared `modules/rtl_buddy/schema/` package — coordinate the module layout with the others.

## Goal

Reimplement the `models.yaml` schema natively so `load-model` (spec [idx-05](../idx-05-selection-expansion.md)) and the filelist generator (`write-filelist`, spec [idx-06](../idx-06-prep.md)) can use the schema by field/method without opening `rtl_buddy`. Preserves the YAML field-name surface so existing `models.yaml` files load drop-in (see [07 settled 1](../07-ambiguities-and-assumptions.md)).

## Deliverables

A single file, `modules/rtl_buddy/schema/model.py`, exporting **`ModelConfig`** — the frozen runtime model object that rides the `model` graph edge (constructed by `load-model`, consumed by `write-filelist`; **not** stored on `TestConfig`).

The raw `@serde` read types **`ModelConfigFileItem`** (the per-entry YAML shape) and **`ModelConfigFile`** (the file wrapper) are **not** here. They are read once by `from_yaml` and never ride a graph edge, so they are defined privately with their sole consumer, `load-model` (spec [05e](05e-load-model.md)), which reads, looks up by name, and **constructs** this `ModelConfig` from the matched item (rtl_buddy folded read + lookup + `path`-stamp into a `ModelConfigLoader` helper; this plan does not port that class). This spec specifies the runtime `ModelConfig` `load-model` builds (below).

### `ModelConfig`

The runtime model for one selected test. Built by `load-model` (spec [05e](05e-load-model.md)) from the matched `ModelConfigFileItem` and emitted on the `model` edge; consumed by `write-filelist` (spec [06b](06b-write-filelist.md)) to construct the compile filelist.

| field      | type           | default    | notes                                                                                                              |
|------------|----------------|------------|--------------------------------------------------------------------------------------------------------------------|
| `name`     | `str`          | required   | Unique model identifier. Copied from the matched `ModelConfigFileItem.name`.                                        |
| `filelist` | `list[str]`    | required   | Paths (relative to the `models.yaml` directory) constituting the model's HDL filelist. Copied from `ModelConfigFileItem.filelist`; consumed by `write-filelist`. |
| `path`     | `str \| None`  | `None`     | Path to the `models.yaml` the model was loaded from. **Set at construction by `load-model`** (spec [05e](05e-load-model.md)) to `str(resolved)` — runtime provenance, never a YAML field (the raw `ModelConfigFileItem` has no `path`). Consumers downstream use it to resolve `filelist` entries relative to the file's directory. Defaults to `None` so a bare `ModelConfig(name, filelist)` is constructible in tests. |

Methods:

| signature                       | returns         | log idiom |
|---------------------------------|-----------------|-----------|
| `get_model_name() -> str`       | `self.name`     | none (see note below). |
| `get_model_path() -> str \| None` | `self.path`   | none.     |
| `get_filelist() -> list[str]`   | `self.filelist` | none.     |

Source: `rtl_buddy/src/rtl_buddy/config/model.py:9-51`.

> **Bug-for-bug or fix?** rtl_buddy's `ModelConfig.get_model_name` at `model.py:30` returns `self.model_name` — an attribute that does not exist on the dataclass (`name` is the actual field). Any caller invoking this method on rtl_buddy would `AttributeError`; in practice no rtl_buddy caller does. This plan should fix the bug while reimplementing (return `self.name`) and flag it in [`divergences.md`](../divergences.md) if any consumer ever starts using the method. Until then, this is informational.

### `ModelConfigFileItem` / `ModelConfigFile` — defined in `load-model`

The raw read shape — `ModelConfigFileItem` (`name` + `filelist`, the per-entry YAML shape, **no** `path`) and `ModelConfigFile` (`rtl-buddy-filetype` discriminator + `models: list[ModelConfigFileItem]`) — is **owned by `load-model`** (spec [05e](05e-load-model.md#raw-schema--conversion-owned-here)), read-once and never on an edge. Their field tables, the read + name-lookup, the construction of `ModelConfig` from the matched item, and the raise-not-`log.fatal` divergence live there. The runtime `ModelConfig` `load-model` builds is defined above.

## Integration

`load-model` (spec [05e](05e-load-model.md)) is the only consumer; it **defines** the raw read types and constructs this `ModelConfig`. The flow:

1. `load-model` receives the `test` edge (the bare `TestConfig` carrying `model`, `model_path`, `suite_dir` from spec [01b](01b-suite-schema.md)).
2. Resolves `resolved = test.suite_dir / test.model_path`.
3. Reads `ModelConfigFile` from `resolved` and looks up `test.model` among the `ModelConfigFileItem`s in `file.models` — read + lookup unrolled into `LoadModelMod.run` (spec [05e](05e-load-model.md)), which **raises** (rather than `log.fatal`-ing) on I/O / parse / schema errors and missing-model lookups so `LoadModelMod` can route a per-test `fail` `result` ([07 settled 10](../07-ambiguities-and-assumptions.md)).
4. **Constructs** `ModelConfig(name=item.name, filelist=item.filelist, path=str(resolved))` and emits it on its own `model` edge — `("model", KeyedValue(test.key, the_model))` — alongside the forwarded `test` edge. **`TestConfig` is not mutated.**

`write-filelist` (spec [06b](06b-write-filelist.md)) `keyed_join`s the `model` edge to `test` by key and reads `model.value.filelist` / `.path` to resolve the model's source list (path is the directory `os.path.dirname(model.path)` since `model.path` is the file). The `keyed_join` guarantees the model is present, so there is no "not yet loaded" case to guard.

## Notable divergences from rtl_buddy

1. **`get_model_name` bug fix.** rtl_buddy returns `self.model_name` (a non-existent attribute); this plan returns `self.name`. Informational only — no current consumer calls this method.
2. **Raw/runtime split; frozen value object.** rtl_buddy makes `ModelConfig` the list-element serde type and mutates `path` onto it in `ModelConfigLoader.get_model`. This plan reads the YAML into the raw `ModelConfigFileItem` (no `path`) and **constructs** a `frozen=True` `ModelConfig` from it with `path` set (spec [05e](05e-load-model.md)) — `path` is runtime provenance set once at construction, never a read field nor an in-place mutation.

(The **failure-routing** divergence — `load-model` raises rather than `log.fatal`-ing so it can route a per-test FAIL — lives with the read + lookup it unrolls in spec [05e](05e-load-model.md#raw-schema--conversion-owned-here); see also [07 settled 10](../07-ambiguities-and-assumptions.md).)

## Tests (`modules/tests/test_model_schema.py`)

These exercise the **runtime `ModelConfig`** owned by this spec. The read + lookup tests (name lookup happy/missing, bad-path/malformed file, empty `models:` list, and the raw `ModelConfigFileItem` carrying no `path`) belong to `load-model`, which owns the raw read types and constructs `ModelConfig` — they live in `test_selection.py` (spec [05e](05e-load-model.md#tests)).

- **Field parity.** A `ModelConfig` constructed from a `models:` entry's `name`/`filelist` (e.g. from `rtl-buddy-proj-template/design/sandbox`) has `name`/`filelist` equal to rtl_buddy's `ModelConfig` over the same YAML entry.
- **Frozen.** `ModelConfig` is `frozen=True`: a direct `model.path = ...` (or any field) assignment raises `FrozenInstanceError`. `load-model` sets `path` at construction (spec [05e](05e-load-model.md)), never by attribute write.
- **`get_model_name` returns `self.name`** (bug fix in this plan verified by direct assertion on a constructed `ModelConfig`).
- **`get_filelist` / `get_model_path`** return `self.filelist` / `self.path` on a constructed `ModelConfig`.

## Acceptance criteria

- Tests pass.
- Constructed `ModelConfig` instances expose `get_filelist()` / `get_model_path()` / `get_model_name()` per the table. (The drop-in load of an unmodified `models.yaml` is exercised by `load-model`, spec [05e](05e-load-model.md), which owns `ModelConfigFileItem`/`ModelConfigFile`.)
- `load-model` (spec [05e](05e-load-model.md)) and `write-filelist` (spec [06b](06b-write-filelist.md)) can be written against this spec without opening `rtl_buddy/src/rtl_buddy/config/model.py`.

## Constraints

- `ModelConfig` is a pure, **`frozen=True`** plain `@dataclass` value object (not `@serde`): no `run()`, no ports, no graph awareness. The `@serde` read shape is `ModelConfigFileItem` (spec [05e](05e-load-model.md)).
- `get_model_name()` must return `self.name` (the rtl_buddy `self.model_name` bug is fixed).
- `path` is **not** a YAML field — `ModelConfig` declares `path: str | None = None`, and `load-model` (spec [05e](05e-load-model.md)) sets it at construction to `str(resolved)`; `write-filelist` (spec [06b](06b-write-filelist.md)) reads `model.path` to resolve `filelist` entries.

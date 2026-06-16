# Spec 01c: Model schema (`models.yaml`)

**Depends on:** none. Can run in parallel with specs 01, 01a, 01b.
**References:** [01-shared-schema](01-shared-schema.md) (umbrella), [01b](01b-suite-schema.md) (`TestConfig.model: ModelConfig | None`), [07 settled 1, 8](../07-ambiguities-and-assumptions.md), TODO #10 (resolution).
**Source:** `rtl_buddy/src/rtl_buddy/config/model.py:1-100` (`ModelConfig`, `ModelConfigFile`, `ModelConfigLoader`).

## Before you start

These are `@serde`-decorated dataclasses that the harness never loads directly — a faithful port
of rtl_buddy's config types, so the authoritative reference is the rtl_buddy `config/*.py` source
this spec cites (anchored to `v1.4.0`, commit `a69d962`). The in-repo `@serde` idiom — nested
types and `field(rename=...)` for verbatim YAML field names — is shown by the config-bearing
example in `docs/modules/implementation.md`; [`02 — payload conventions`](../02-payload-conventions.md)
holds the canonical type and `is_pass()` table the port must match. All four schema specs (`01`,
`01a`, `01b`, `01c`) build into the shared `modules/rtl_buddy/schema/` package — coordinate the
module layout with the others.

## Goal

Reimplement the `models.yaml` schema natively so `load-model` (spec
[05](05-selection-expansion-modules.md)) and the filelist generator (`write-filelist`,
spec [06](06-prep-modules.md)) can use the schema by field/method without opening
`rtl_buddy`. Preserves the YAML field-name surface so existing `models.yaml` files
load drop-in (see [07 settled 1](../07-ambiguities-and-assumptions.md)).

## Deliverables

A single file, `modules/rtl_buddy/schema/model.py`, exporting `ModelConfig`,
`ModelConfigFile`, and `ModelConfigLoader`.

### `ModelConfig`

One entry per element in `models.yaml`'s `models:` list. Attached to
`TestConfig.model` by `load-model` (spec [05](05-selection-expansion-modules.md))
after lookup by name; consumed by `write-filelist` (spec [06](06-prep-modules.md))
to construct the compile filelist.

| field      | type           | YAML rename | default    | notes                                                                                                              |
|------------|----------------|-------------|------------|--------------------------------------------------------------------------------------------------------------------|
| `name`     | `str`          | (none)      | required   | Unique model identifier inside the file. Matched by `ModelConfigLoader.get_model(model_name)`.                     |
| `filelist` | `list[str]`    | (none)      | required   | Paths (relative to the `models.yaml` directory) constituting the model's HDL filelist. Consumed by `write-filelist`. |
| `path`     | `str \| None`  | (none)      | `None`     | Path to the `models.yaml` the model was loaded from. **Set by `ModelConfigLoader.get_model`** after lookup, not by the YAML. Consumers downstream use it to resolve `filelist` entries relative to the file's directory. |

Methods:

| signature                       | returns         | log idiom |
|---------------------------------|-----------------|-----------|
| `get_model_name() -> str`       | `self.name`     | none (see note below). |
| `get_model_path() -> str \| None` | `self.path`   | none.     |
| `get_filelist() -> list[str]`   | `self.filelist` | none.     |

Source: `rtl_buddy/src/rtl_buddy/config/model.py:9-51`.

> **Bug-for-bug or fix?** rtl_buddy's `ModelConfig.get_model_name` at
> `model.py:30` returns `self.model_name` — an attribute that does not exist on the
> dataclass (`name` is the actual field). Any caller invoking this method on rtl_buddy
> would `AttributeError`; in practice no rtl_buddy caller does. Plan B should fix the
> bug while reimplementing (return `self.name`) and flag it under "Notable
> divergences" in [07](../07-ambiguities-and-assumptions.md) if any consumer ever
> starts using the method. Until then, this is informational.

### `ModelConfigFile`

The serde-decorated top-level type read straight from `models.yaml`.

| field                | type                          | YAML rename          | default                  | notes                                                                                  |
|----------------------|-------------------------------|----------------------|--------------------------|----------------------------------------------------------------------------------------|
| `rtl_buddy_filetype` | `Literal['model_config']`     | `rtl-buddy-filetype` | required                 | Discriminator; serde raises on mismatch (caught by `ModelConfigLoader` → `log.fatal`). |
| `models`             | `list[ModelConfig]`           | (none)               | `field(default_factory=list)` | Empty `models:` is legal and produces a no-op file (no models retrievable).            |

Source: `rtl_buddy/src/rtl_buddy/config/model.py:53-63`.

### `ModelConfigLoader`

Helper that reads `models.yaml` once and answers `get_model(name)` lookups. Owned by
`load-model` (spec [05](05-selection-expansion-modules.md)); not a graph node itself.

Construction (`__init__(path: str)`):

1. `self.path = path`.
2. Open + `from_yaml(ModelConfigFile, ...)`. Any exception → `log.fatal(f'Failed to load "{path}" {e}')`. Mirrors `model.py:76-81`. Specific classes in play: `FileNotFoundError`, `PermissionError`, `IsADirectoryError` (file I/O); `serde.SerdeError` / `yaml.YAMLError` (parse); `TypeError` / `KeyError` (schema mismatch).
3. `self.models = data.models` (the list).

Method:

| signature                                       | returns                          | log idiom                                                                                                                                            |
|-------------------------------------------------|----------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| `get_model(model_name: str) -> ModelConfig`     | The matching `ModelConfig`, with its `path` field mutated in place to `self.path` (so downstream consumers know which `models.yaml` it came from). | `log.fatal(f"model '{model_name}' not found")` if no `ModelConfig` in `self.models` has `name == model_name`. Mirrors `model.py:83-100`.          |

Note the **`path` mutation side effect** at `model.py:97`: `get_model` writes
`model.path = self.path` before returning. Preserve this — `write-filelist` (spec
[06](06-prep-modules.md)) relies on `model.path` being set to resolve `filelist`
entries relative to the `models.yaml`'s directory.

Source: `rtl_buddy/src/rtl_buddy/config/model.py:66-100`.

## Plan B integration

`load-model` (spec [05](05-selection-expansion-modules.md)) is the only direct
consumer of `ModelConfigLoader`. The flow:

1. `load-model` receives `ctx` (with `ctx["test"]` carrying `model_name`,
   `model_path`, `suite_dir` from spec [01b](01b-suite-schema.md)).
2. Resolves `resolved = ctx["test"].suite_dir / ctx["test"].model_path`.
3. Constructs `ModelConfigLoader(str(resolved))` — `__init__`'s broad-exception catch
   converts I/O / parse / schema errors to `log.fatal`, but in Plan B these are
   **port-routed `fail` `result`** (spec [05](05-selection-expansion-modules.md) `LoadModelMod`
   failure-handling block + [07 settled 10](../07-ambiguities-and-assumptions.md)). The
   reimplementation should therefore **let exceptions propagate from `ModelConfigLoader`**
   rather than calling `log.fatal` inside the loader itself; the `LoadModelMod` wrapper
   catches and routes. This is a deliberate divergence from rtl_buddy at the *loader*
   layer, motivated by Plan B's per-test FAIL routing.
4. Calls `loader.get_model(ctx["test"].model_name)`. A missing-model lookup similarly
   propagates rather than crit-logging; `LoadModelMod` catches and routes.
5. Assigns `ctx["test"].model = the_model` and emits `("default", ctx)`.

`write-filelist` (spec [06](06-prep-modules.md)) consumes `ctx["test"].get_model()`
— at that point in the graph, `load-model` has fired and `ctx["test"].model` is a
populated `ModelConfig`. It reads `.filelist` and `.path` to resolve the model's
source list (path is the directory `os.path.dirname(model.path)` since `model.path`
is the file).

## Notable divergences from rtl_buddy

1. **Failure routing.** rtl_buddy's `ModelConfigLoader.__init__` and `get_model` call
   `logger.critical(...)` directly — aborting the whole run on any per-test
   `models.yaml` issue. Plan B's reimplementation **raises** instead, so `LoadModelMod`
   can catch and emit a per-test `fail` `result` (see [07 settled
   10](../07-ambiguities-and-assumptions.md)). This is the loader-layer half of the
   broader "per-test config-domain failures route as per-test FAIL" divergence already
   recorded in [07 — Notable divergences](../07-ambiguities-and-assumptions.md).
2. **`get_model_name` bug fix.** rtl_buddy returns `self.model_name` (a
   non-existent attribute); Plan B returns `self.name`. Informational only — no
   current consumer calls this method.

## Tests (`modules/tests/test_model_schema.py`)

- **Round-trip.** Load an unmodified rtl_buddy `models.yaml` (e.g. from
  `rtl-buddy-proj-template/design/sandbox`); for each `models:` entry, every field
  round-trips equal to rtl_buddy's `ModelConfig` constructed over the same YAML.
- **`get_model` happy path.** A fixture file with two models; `get_model("modelA")`
  returns the `ModelConfig` with `name == "modelA"` and `path == <the loader's path>`
  (assert the mutation happened).
- **`get_model` missing name.** `get_model("nonexistent")` raises rather than calling
  `log.fatal` (Plan B divergence). Implementation choice: raise `KeyError` or a
  custom `ModelNotFoundError` — either is fine as long as `LoadModelMod` catches
  broadly.
- **`ModelConfigLoader` ctor — bad path.** `ModelConfigLoader("/no/such/file.yaml")`
  raises (FileNotFoundError) rather than calling `log.fatal`.
- **`ModelConfigLoader` ctor — malformed YAML.** A fixture with bad YAML similarly
  propagates.
- **Empty `models:` list.** A `models.yaml` with `models: []` loads successfully;
  any `get_model(...)` call raises.
- **`get_model_name` returns `self.name`** (Plan B bug fix verified by direct
  assertion).

## Acceptance criteria

- Tests pass.
- Loading an unmodified rtl_buddy `models.yaml` produces `ModelConfig` instances
  whose `get_filelist()` / `get_model_path()` return values equal to rtl_buddy's
  on the same input.
- `load-model` (spec [05](05-selection-expansion-modules.md)) and `write-filelist`
  (spec [06](06-prep-modules.md)) can be written against this spec without opening
  `rtl_buddy/src/rtl_buddy/config/model.py`.

## Constraints

- Preserve the `rtl-buddy-filetype` rename (keep the hyphen); do **not** Pythonify it.
- `ModelConfigLoader.__init__` and `get_model` must **raise** on I/O / parse / schema error
  and on a missing model — **not** `log.fatal`. This is the deliberate loader-layer
  divergence from rtl_buddy that lets `LoadModelMod` (spec [05e](05e-load-model.md)) catch and
  route a per-test FAIL. Do not collapse it back to `log.fatal`.
- `get_model` must mutate `model.path = self.path` in place before returning — preserve this
  side effect; `write-filelist` (spec [06b](06b-write-filelist.md)) reads `model.path` to
  resolve `filelist` entries.
- `get_model_name()` must return `self.name` (the rtl_buddy `self.model_name` bug is fixed).
- An empty `models:` list is legal (loads fine); any `get_model(...)` against it raises.
- Pure value/loader objects: no `run()`, no ports, no graph awareness.

## Notes

YAML `field(rename=...)` targets are the **public surface** for downstream rtl_buddy
users — do **not** Pythonify them. `rtl-buddy-filetype` keeps the hyphen.

The `ModelConfig.path` field is `None` on the YAML side and **mutated** by
`ModelConfigLoader.get_model` before return. This is unusual for a value type;
preserve the behaviour rather than introducing a new wrapper, because
`write-filelist` reads it as `model.path` directly.

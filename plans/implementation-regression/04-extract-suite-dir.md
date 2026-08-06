# Spec 04: extract-suite-dir (`ExtractSuiteDirMod`)

**Depends on:** nothing — the module is self-contained.
**References:** [00-overview](00-overview.md) — per-suite `base_dir` and `logs_dir` problem statement and solution; `graphs/test.yaml` — `work-dir` and `ensure-logs` nodes this replaces.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms, `KeyedValue`).

## Goal

Extract `suite_dir` from each `TestConfig`, create the logs directory, and emit `base_dir` and `logs_dir` as keyed values. The `base_dir` port feeds both `base_dir` and `work_dir` destination ports on downstream consumers — the values are identical, only the destination port names differ. This replaces `work-dir` (which emits `Path.cwd()` once) and `ensure-logs` (which creates `<work_dir>/logs/` once) from the test graph.

## Why this module exists

In the test graph, `work-dir` emits `Path.cwd().resolve()` once, and `ensure-logs` creates `<work_dir>/logs/` once. Both fan out as persistent inputs. Regression has no single CWD — each suite's working directory is `parse-suite-config`'s `suite_dir`, already stamped on every `TestConfig.suite_dir`. A persistent input is set once and shared across all invocations — it cannot vary per suite.

`expand-runs` re-keys everything from `test_key` to `test_key#run_id`. A keyed `base_dir` emitted with `test_key` won't match `test_key#run_id` in `keyed_join` on post-fan-out nodes. Since `TestConfig.suite_dir` rides the object through the fan-out, the solution is two instances:

- **`extract-dir`** (after `gate-pre`): emits with key `test_key`, serves pre-fan-out consumers.
- **`extract-dir-post`** (after `runs`): receives the re-keyed `test` from `expand-runs`, emits with key `test_key#run_id`, serves post-fan-out consumers.

## Surface

```
contract:          default with persistent_inputs: [logs_dir]
inputs:            test:TestConfig, logs_dir:str = "logs"
outputs:           ("base_dir", KeyedValue), ("logs_dir", KeyedValue)
```

```python
class ExtractSuiteDirMod:
    def run(self, test:TestConfig, logs_dir:str = "logs"):
        logs_path = (test.suite_dir / logs_dir).resolve()
        try:
            logs_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            log.fatal("logs_dir_create_failed", path=str(logs_path), exc_info=e)
        yield ("base_dir", KeyedValue(test.key, test.suite_dir))
        yield ("logs_dir", KeyedValue(test.key, logs_path))
```

The `logs_dir` string comes from the CLI edge as a persistent input. `test` is the streaming input. `mkdir -p` is idempotent, so per-test invocations (including the post-fan-out instance) are harmless.

## Algorithm

1. Resolve `test.suite_dir / logs_dir` to an absolute path.
2. Create the directory (`parents=True, exist_ok=True`). On `OSError` → `log.fatal("logs_dir_create_failed")`.
3. Yield `("base_dir", KeyedValue(test.key, test.suite_dir))`.
4. Yield `("logs_dir", KeyedValue(test.key, logs_path))`.

## Downstream wiring changes

In the regression graph, downstream nodes that received `work_dir`, `base_dir`, or `logs_dir` as persistent inputs from `work-dir`/`ensure-logs` instead receive them as keyed values from `extract-dir` or `extract-dir-post`:

| Consumer | Dst port | Was persistent from | Now keyed from (src port) |
|---|---|---|---|
| `cc-build` | `work_dir` | `work-dir` | `extract-dir` (`base_dir`) |
| `cc-build` | `logs_dir` | `ensure-logs` | `extract-dir` (`logs_dir`) |
| `cc-run` | `work_dir` | `work-dir` | `extract-dir` (`base_dir`) |
| `fl-tb` | `base_dir` | `work-dir` | `extract-dir` (`base_dir`) |
| `fl-norm` | `base_dir` | `work-dir` | `extract-dir` (`base_dir`) |
| `fl-path` | `work_dir` | `work-dir` | `extract-dir` (`base_dir`) |
| `sim-run` | `work_dir` | `work-dir` | `extract-dir-post` (`base_dir`) |
| `randseed` | `work_dir` | `work-dir` | `extract-dir-post` (`base_dir`) |
| `link-latest` | `work_dir` | `work-dir` | `extract-dir-post` (`base_dir`) |
| `sim-build` | `logs_dir` | `ensure-logs` | `extract-dir-post` (`logs_dir`) |
| `seed` | `logs_dir` | `ensure-logs` | `extract-dir-post` (`logs_dir`) |

No downstream module changes — only graph-YAML contract configs (`persistent_inputs` removal, `unwrap: true` additions on `randseed`/`link-latest`, and `cc-run`'s contract switch to `keyed_join`).

## Deliverables

- `ExtractSuiteDirMod` in `modules/rtl_buddy/setup.py`.
- **Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`:
  ```yaml
    - { name: extract-suite-dir, class_name: ExtractSuiteDirMod }
  ```

## Tests

In `modules/tests/test_setup.py`.

- `test` with `key="sandbox/basic"`, `suite_dir=Path("/a/b/sandbox")`, `logs_dir="logs"` → yields `("base_dir", KeyedValue("sandbox/basic", Path("/a/b/sandbox")))`, `("logs_dir", KeyedValue("sandbox/basic", Path("/a/b/sandbox/logs")))`. The `logs/` directory is created.
- `logs_dir="out"` → `logs_dir` path is `suite_dir / "out"`.
- Idempotent: calling twice with the same `suite_dir` does not error (`mkdir -p`).
- `mkdir` raises `OSError` → `log.fatal("logs_dir_create_failed")`.

## Acceptance criteria

- All four test cases pass.
- `extract-suite-dir` → `ExtractSuiteDirMod` resolves in the manifest.
- The `logs/` directory is created on each invocation (idempotent).
- Emitted `KeyedValue`s carry the correct `test.key`.

## Docs

Add a `docs/modules/extract-suite-dir.md` page and update `docs/modules/index.md` to include it. Follow `docs/creating-documentation.md` and `docs/modules/doc-structure.md`.

## Constraints

- **No graph knowledge.** The module does not know about `cc-build`, `sim-run`, or any consumer; it extracts directory paths from a `TestConfig`.
- **Contract: `default` with `persistent_inputs: [logs_dir]`.** The CLI `logs_dir` string arrives once and persists; `test` streams per test.
- **`mkdir -p` is idempotent.** Multiple tests from the same suite create the same directory without error.
- **No downstream module changes.** Only graph-YAML contract configs change (removing ports from `persistent_inputs`).

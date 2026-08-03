# Spec 04: extract-suite-dir (`ExtractSuiteDirMod`)

**Depends on:** nothing — the module is self-contained.
**References:** [00-overview](00-overview.md) — per-suite `work_dir` and `logs_dir` problem statement and solution; `graphs/test.yaml` — `work-dir` and `ensure-logs` nodes this replaces.

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms, `KeyedValue`).

## Goal

Extract `suite_dir` from each `TestConfig`, create the logs directory, and emit `work_dir`, `base_dir`, and `logs_dir` as keyed values. This replaces `work-dir` (which emits `Path.cwd()` once) and `ensure-logs` (which creates `<work_dir>/logs/` once) from the test graph.

## Why this module exists

In the test graph, `work-dir` emits `Path.cwd().resolve()` once, and `ensure-logs` creates `<work_dir>/logs/` once. Both fan out as persistent inputs. Regression has no single CWD — each suite's working directory is `parse-suite-config`'s `suite_dir`, already stamped on every `TestConfig.suite_dir`. A persistent input is set once and shared across all invocations — it cannot vary per suite.

`expand-runs` re-keys everything from `test_key` to `test_key#run_id`. A keyed `work_dir` emitted with `test_key` won't match `test_key#run_id` in `keyed_join` on post-fan-out nodes. Since `TestConfig.suite_dir` rides the object through the fan-out, the solution is two instances:

- **`extract-dir`** (after `gate-pre`): emits with key `test_key`, serves pre-fan-out consumers.
- **`extract-dir-post`** (after `runs`): receives the re-keyed `test` from `expand-runs`, emits with key `test_key#run_id`, serves post-fan-out consumers.

## Surface

```
contract:          default with persistent_inputs: [logs_dir]
inputs:            test:TestConfig, logs_dir:str = "logs"
outputs:           ("work_dir", KeyedValue), ("base_dir", KeyedValue), ("logs_dir", KeyedValue)
```

```python
class ExtractSuiteDirMod:
    def run(self, test:TestConfig, logs_dir:str = "logs"):
        logs_path = (test.suite_dir / logs_dir).resolve()
        logs_path.mkdir(parents=True, exist_ok=True)
        yield ("work_dir", KeyedValue(test.key, test.suite_dir))
        yield ("base_dir", KeyedValue(test.key, test.suite_dir))
        yield ("logs_dir", KeyedValue(test.key, logs_path))
```

The `logs_dir` string comes from the CLI edge as a persistent input. `test` is the streaming input. `mkdir -p` is idempotent, so per-test invocations (including the post-fan-out instance) are harmless.

## Algorithm

1. Resolve `test.suite_dir / logs_dir` to an absolute path.
2. Create the directory (`parents=True, exist_ok=True`).
3. Yield `("work_dir", KeyedValue(test.key, test.suite_dir))`.
4. Yield `("base_dir", KeyedValue(test.key, test.suite_dir))`.
5. Yield `("logs_dir", KeyedValue(test.key, logs_path))`.

## Downstream wiring changes

In the regression graph, downstream nodes that received `work_dir`, `base_dir`, or `logs_dir` as persistent inputs from `work-dir`/`ensure-logs` instead receive them as keyed values from `extract-dir` or `extract-dir-post`:

| Consumer | Port | Was persistent from | Now keyed from |
|---|---|---|---|
| `cc-build` | `work_dir` | `work-dir` | `extract-dir` |
| `cc-build` | `logs_dir` | `ensure-logs` | `extract-dir` |
| `cc-run` | `work_dir` | `work-dir` | `extract-dir` |
| `fl-tb` | `base_dir` | `work-dir` | `extract-dir` |
| `fl-norm` | `base_dir` | `work-dir` | `extract-dir` |
| `fl-path` | `work_dir` | `work-dir` | `extract-dir` |
| `sim-run` | `work_dir` | `work-dir` | `extract-dir-post` |
| `randseed` | `work_dir` | `work-dir` | `extract-dir-post` |
| `link-latest` | `work_dir` | `work-dir` | `extract-dir-post` |
| `sim-build` | `logs_dir` | `ensure-logs` | `extract-dir-post` |
| `seed` | `logs_dir` | `ensure-logs` | `extract-dir-post` |

No downstream module changes — only graph-YAML contract configs (removing ports from `persistent_inputs`).

## Deliverables

- `ExtractSuiteDirMod` in `modules/rtl_buddy/setup.py`.
- **Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`:
  ```yaml
    - { name: extract-suite-dir, class_name: ExtractSuiteDirMod }
  ```

## Tests

In `modules/tests/test_setup.py`.

- `test` with `key="sandbox/basic"`, `suite_dir=Path("/a/b/sandbox")`, `logs_dir="logs"` → yields `("work_dir", KeyedValue("sandbox/basic", Path("/a/b/sandbox")))`, `("base_dir", KeyedValue("sandbox/basic", Path("/a/b/sandbox")))`, `("logs_dir", KeyedValue("sandbox/basic", Path("/a/b/sandbox/logs")))`. The `logs/` directory is created.
- `logs_dir="out"` → `logs_dir` path is `suite_dir / "out"`.
- Idempotent: calling twice with the same `suite_dir` does not error (`mkdir -p`).

## Acceptance criteria

- All three test cases pass.
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

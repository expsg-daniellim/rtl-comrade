# `extract-suite-dir`

**Class:** `ExtractSuiteDirMod` (`modules/rtl_buddy/setup.py`)

[Back to index](index.md)

Extracts a test's `suite_dir`, creates `suite_dir/logs_dir` (idempotently), and emits both as keyed values. Regression has no single working directory, so this replaces the once-only [work-dir](work-dir.md) and [ensure-logs-dir](ensure-logs-dir.md) persistent inputs with per-test keyed values.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `test` | `TestConfig` | — | the test whose `suite_dir` to extract (per-test edge) |
| `logs_dir` | `str` | `"logs"` | logs subdirectory name (CLI `--logs-dir`, persistent) |

## Outputs

`base_dir` — `KeyedValue(test.key, test.suite_dir)`; `logs_dir` — `KeyedValue(test.key, <resolved suite_dir/logs_dir>)`. Both fire once per invocation.

## Failure routing

All four are `log.fatal`:

- `logs_dir_path_invalid` — `ValueError` resolving the logs path (e.g. an embedded null character in `logs_dir`)
- `logs_dir_path_symlink_loop` — `RuntimeError` resolving the logs path (symlink loop, Python ≤ 3.12)
- `logs_dir_path_os_error` — `OSError` resolving the logs path (symlink loop, Python ≥ 3.13)
- `logs_dir_create_failed` — `OSError` creating the logs directory

## Graph node

Two instances in the `regression` graph, both contract `default` with `persistent_inputs: [logs_dir]`: `extract-dir` (after `gate-pre`, keyed by `test_key`) serves pre-fan-out consumers, and `extract-dir-post` (after `runs`, keyed by `test_key#run_id`) serves post-fan-out consumers. The `base_dir` port feeds both `base_dir` and `work_dir` destination ports downstream.

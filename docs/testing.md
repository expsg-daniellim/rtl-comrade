# Running Tests

## After making changes

Run this two-stage procedure for the section you changed. Stage 1 confirms the code works; stage 2 confirms all of it is tested.

### Harness (`src/rtl_comrade/`)

The contract test suite must be included in both stages because `contracts/tests/` exercises the deferred-delivery paths in `src/rtl_comrade/testing.py` (the `PortTestInput(delay=N)` and `_feeder` code paths) that `tests/` alone does not reach.

**Stage 1 — correctness:**

```bash
uv run pytest tests/ contracts/tests/
```

**Stage 2 — coverage:**

```bash
uv run pytest tests/ contracts/tests/ --cov=src/rtl_comrade --cov-report=term-missing
```

Expected result: 100% on all files except the two accepted misses listed below. Any other line number in the `Missing` column needs a test.

When adding a new harness module, add a corresponding test file under `tests/unit/`. The current module-to-test-file mapping is:

| Module | Test file |
|---|---|
| `api.py` | `tests/unit/test_api.py` |
| `port.py` | `tests/unit/test_port.py` |
| `structure.py` | `tests/unit/test_structure.py` |
| `config.py` | `tests/unit/test_config.py` |
| `loader_utils.py` | `tests/unit/test_loader_utils.py` |
| `loader_plugin.py` | `tests/unit/test_loader_plugin.py` |
| `loader_logger.py` | `tests/unit/test_loader_logger.py` |
| `logging.py` | `tests/unit/test_logging.py` |
| `validation.py` | `tests/unit/test_validation.py` |
| `contract_default.py` | `tests/unit/test_contract_default.py` |
| `module.py` | `tests/unit/test_module.py` |
| `node.py` | `tests/unit/test_node.py` |
| `graph.py` | `tests/unit/test_graph.py` |
| `app.py` | `tests/unit/test_app.py` |
| `testing.py` (contract harness) | `tests/unit/test_contract_harness.py` |
| `testing.py` (module harness) | `tests/unit/test_module_harness.py` |

Integration tests covering the full `Graph.from_file → Graph.run` path live in `tests/integration/`. They write temporary plugin `.py` files to `tmp_path` and construct `GraphConfig` objects directly (or `GraphFileConfig` objects converted via `GraphConfig.from_file_config` for tests that exercise CLI-edge expansion); they never depend on on-disk graph YAML files.

### Contracts (`contracts/`)

**Stage 1 — correctness:**

```bash
uv run pytest contracts/tests/
```

**Stage 2 — coverage:**

```bash
uv run pytest contracts/tests/ --cov=contracts --cov-report=term-missing
```

Expected result: 100% on all files. When adding a new contract, add a corresponding test file under `contracts/tests/` and reach 100% before merging. The contract testing harness (`run_contract_scenario`) handles the boilerplate; see `docs/contracts/testing.md` for coverage targets and patterns.

Contract tests construct ports and `ContractPort` adapters directly or via `run_contract_scenario()`; they never instantiate a `Node` or `Graph`.

### Modules (`modules/`)

**Stage 1 — correctness:**

```bash
uv run pytest modules/tests/
```

**Stage 2 — coverage:**

```bash
uv run pytest modules/tests/ --cov=modules --cov-report=term-missing
```

Expected result: 100% on all files. When adding a new module, add a corresponding test file under `modules/tests/`. Use `run_module_scenario` from `rtl_comrade.testing` for straightforward input/output cases.

---

## Full suite

To run every test at once with no coverage (useful as a final sanity check across all three sections):

```bash
uv run pytest tests/ contracts/tests/ modules/tests/
```

---

## Conventions

- `asyncio_mode = "auto"` is set in `pyproject.toml`; async tests need no extra decoration.
- Tests that exercise fatal or error log paths must use the `logging_handler` fixture (defined in `tests/conftest.py`). Fatal calls (`log.critical` / `log.fatal`) raise `typer.Exit(1)` (a `BaseException` subclass via `click.Exit`, distinct from `SystemExit`); assert them with `pytest.raises(typer.Exit)`. Error calls set `handler.failure = True` without raising.

---

## Accepted coverage misses

Five locations in the harness are intentionally excluded from coverage. All are suppressed at source so the report reads 100% with no `Missing` entries — do not write tests to cover them.

### `src/rtl_comrade/__main__.py` — entire file, excluded via `omit`

`__main__.py` is the OS-level entry point for `python -m rtl_comrade` and the `rtl-comrade` console script. The test suite drives `App` directly and never spawns a subprocess, so this file is never imported during a test run. The logic it delegates to (`App().run()`) is fully covered by `tests/unit/test_app.py`.

The file is excluded entirely via `[tool.coverage.run] omit` in `pyproject.toml` — line-level pragmas cannot reach a file that is never imported.

### `src/rtl_comrade/logging.py` — `HarnessLogger.fatal` and `.critical` bodies, excluded via `# pragma: no cover`

```python
def fatal(self, event=None, *args, **kw) -> NoReturn:  # pragma: no cover
    super().fatal(event, *args, **kw)
    raise AssertionError('unreachable')

def critical(self, event=None, *args, **kw) -> NoReturn:  # pragma: no cover
    super().critical(event, *args, **kw)
    raise AssertionError('unreachable')
```

`LoggingFatalHandler.emit()` raises `typer.Exit(1)` on every `CRITICAL` record before control can return to `super().fatal()`. These method bodies exist solely to satisfy `ty`'s control-flow analysis, which requires `NoReturn`-annotated methods to contain a syntactically reachable termination. Covering them would require suppressing the very handler that implements the harness failure model.

### `src/rtl_comrade/graph.py` — `Graph.run()` body, excluded via `# pragma: no cover`

```python
def run(self):  # pragma: no cover
    ...
    log.fatal("dummy_run_called", context='harness.graph.cli')
```

`Graph.run()` is a intentional stub that guards against the old `asyncio.run(graph.run())` call pattern. The correct entry point is `Graph.construct_run()`. The stub exists to produce a clear fatal log if the old pattern is ever used by mistake; it is unreachable in normal operation and untestable without defeating its own purpose.

### `src/rtl_comrade/graph.py` — `missing_runs` guard and non-definite string-port fallback, excluded via `# pragma: no cover`

`missing_runs` (lines 73–74): the guard `not (hasattr(mod.Module, 'run') and callable(...))` can never be True at runtime — `GraphModule.from_module` is called on every module before this check and always raises (`AttributeError` for a missing `run`, `typer.Exit` for a non-callable one) before returning an entry to `module_mappings`.

`dst_name = edge.dst.port` (line 131): the fallback for a non-definite-input node addressed by a string port that was not found in `get_canonical_port`. Since graph assembly pre-builds every incoming string port into `node.ports` at line 97, `get_canonical_port` always finds them and this branch is never reached.

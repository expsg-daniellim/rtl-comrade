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
| `loader.py` | `tests/unit/test_loader.py` |
| `validation.py` | `tests/unit/test_validation.py` |
| `contract_default.py` | `tests/unit/test_contract_default.py` |
| `node.py` | `tests/unit/test_node.py` |
| `graph.py` | `tests/unit/test_graph.py` |
| `app.py` | `tests/unit/test_app.py` |
| `testing.py` (contract harness) | `tests/unit/test_contract_harness.py` |
| `testing.py` (module harness) | `tests/unit/test_module_harness.py` |

Integration tests covering the full `Graph.from_file → Graph.run` path live in `tests/integration/`. They write temporary plugin `.py` files to `tmp_path` and construct `GraphConfig` objects directly; they never depend on on-disk graph YAML files.

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
- Tests that exercise fatal or error log paths must use the `logging_handler` fixture (defined in `tests/conftest.py`). Fatal calls (`log.critical` / `log.fatal`) raise `SystemExit(1)`; assert them with `pytest.raises(SystemExit)`. Error calls set `handler.failure = True` without raising.

---

## Accepted coverage misses

Two lines in the harness will always show as uncovered. Do not write tests to cover them.

### `src/rtl_comrade/__main__.py` — entire file (0%)

```
Missing: 3-18
```

`__main__.py` is the OS-level entry point for `python -m rtl_comrade` and the `rtl-comrade` console script. The test suite drives `App` directly and never spawns a subprocess, so this file is never imported during a test run. The logic it delegates to (`App().run()`) is fully covered by `tests/unit/test_app.py`.

### `src/rtl_comrade/logging.py` — lines 18–19 and 22–23 (88%)

```
Missing: 18-19, 22-23
```

These are the `raise AssertionError('unreachable')` statements at the end of `HarnessLogger.fatal()` and `HarnessLogger.critical()`:

```python
def fatal(self, event=None, *args, **kw) -> NoReturn:
    super().fatal(event, *args, **kw)
    raise AssertionError('unreachable')   # line 19 — never reached at runtime

def critical(self, event=None, *args, **kw) -> NoReturn:
    super().critical(event, *args, **kw)
    raise AssertionError('unreachable')   # line 23 — never reached at runtime
```

`LoggingFatalHandler.emit()` raises `SystemExit(1)` on every `CRITICAL` record before control can return to `super().fatal()`. These statements exist solely to satisfy `ty`'s control-flow analysis, which requires `NoReturn`-annotated methods to contain a syntactically reachable termination. Covering them would require suppressing the very handler that implements the harness failure model.

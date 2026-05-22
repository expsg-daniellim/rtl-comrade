# Testing Modules

For implementation details, see [implementation.md](implementation.md).

Modules can be tested in isolation using `run_module_scenario` from `rtl_comrade.testing`.

The harness drives the module's `run(...)` method directly, without a graph or contract. You supply a sequence of input dicts (one per invocation) and the expected emissions per port.

## Loading module classes

The `modules/` directory is a plugin directory, not a Python package. Load module classes with `importlib.util` to avoid name conflicts with the standard library (notably `io`):

```python
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("modules_funcs", Path(__file__).parent.parent / "funcs.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
AddMod = _mod.AddMod
```

## conftest setup

Place a `conftest.py` next to your test files to make the `logging_handler` fixture available:

```python
# modules/tests/conftest.py
from rtl_comrade.testing import logging_handler  # noqa: F401
```

## Basic example

```python
from rtl_comrade.testing import run_module_scenario

async def test_add_integers():
    await run_module_scenario(
        AddMod,
        input_sequence=[{"a": 3, "b": 4}],
        expected_emissions={"default": [7]},
    )
```

`input_sequence` is a list of dicts — one per `run(...)` invocation. Each dict maps parameter name to raw value (the same values the module sees after the harness unwraps payloads).

`expected_emissions` maps port name to an ordered list of expected values. A port absent from the dict is expected to produce no emissions.

## Generator module

Emissions from a single invocation are collected in order alongside emissions from subsequent invocations:

```python
async def test_fileread_yields_lines(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("hello\nworld\n")
    await run_module_scenario(
        FileReadMod,
        input_sequence=[{}],
        expected_emissions={"default": ["hello\n", "world\n"]},
        config=FileReadMod.Config(file=str(f)),
    )
```

## Named-port module

```python
async def test_router_positive():
    await run_module_scenario(
        SplitMod,
        input_sequence=[{"a": 5}],
        expected_emissions={"positive": [5]},
    )
```

## Multi-step sequence

Pass multiple dicts to drive several invocations. Emissions are accumulated across all steps in call order:

```python
async def test_add_multi_step():
    await run_module_scenario(
        AddMod,
        input_sequence=[{"a": 1, "b": 2}, {"a": 10, "b": 20}],
        expected_emissions={"default": [3, 30]},
    )
```

## Source modules

A module with no `run(...)` parameters is a source node. Pass a single empty dict. The harness runs it once and stops, matching the graph runtime:

```python
async def test_source_emits_once():
    await run_module_scenario(
        SourceMod,
        input_sequence=[{}],
        expected_emissions={"default": [99]},
    )
```

## Config-bearing modules

Pass a `Config` instance directly as the `config` keyword argument. The harness passes it as-is, without serde deserialization:

```python
async def test_fileread_lines(tmp_path):
    f = tmp_path / "data.txt"
    f.write_text("line one\n")
    await run_module_scenario(
        FileReadMod,
        input_sequence=[{}],
        expected_emissions={"default": ["line one\n"]},
        config=FileReadMod.Config(file=str(f)),
    )
```

## Testing error paths

`ERROR` log calls set `logging_handler.failure = True` without raising. Assert on that after the scenario:

```python
async def test_invalid_op_logs_error(logging_handler):
    await run_module_scenario(
        ALUMod,
        input_sequence=[{"a": 10, "b": 3, "op": 2}],
        expected_emissions={},
    )
    assert logging_handler.failure is True
```

`CRITICAL` (and `fatal`) log calls raise `SystemExit(1)`. Use `pytest.raises`:

```python
async def test_file_not_found_is_fatal(logging_handler):
    with pytest.raises(SystemExit):
        await run_module_scenario(
            FileReadMod,
            input_sequence=[{}],
            expected_emissions={},
            config=FileReadMod.Config(file="/nonexistent.txt"),
        )
```

The `logging_handler` fixture is required for both cases; without it, the structlog calls are not intercepted.

## Coverage Target

Run coverage against a single module file:

```bash
uv run pytest modules/tests/test_mymodule.py --cov=modules/mymodule.py --cov-report=term-missing
```

The missing-lines report shows exactly which branches remain uncovered. Aim for 100% on every module file before merging.

Key branches to cover:

**Output ports**

- Every named port your module can emit on — one test per port.
- The `None`-returning path if your module ever returns `None` (emits nothing).

**Conditional logic**

- Each branch of any `if`/`elif`/`else` inside `run(...)`. For a module like `CompareMod` that routes to `"gt"`, `"lt"`, or `"eq"`, each branch needs at least one test.

**Generator behavior**

- At least one test that exercises the full sequence a generator emits in a single invocation.
- If the generator has early-exit conditions, test them too.

**Stateful modules**

- Multi-step sequences via `input_sequence` to drive the module through each state transition. A module that accumulates state across calls needs tests that verify both early-call and late-call behavior.

**Error and fatal paths**

- If your module logs `ERROR` for a bad input or unsupported operation, include a test that passes that input and asserts `logging_handler.failure is True`.
- If your module calls `log.fatal` / `log.critical`, include a test with `pytest.raises(SystemExit)`.

**Config validation**

- If `__init__` validates config fields, include at least one test for a valid config and one that triggers each validation failure.

**`finalise` teardown**

- If your module defines `finalise()`, test that it runs after all `run(...)` invocations: check side effects (flushed state, closed resources, etc.) after `run_module_scenario` returns.
- If `finalise()` can raise, include a test that triggers that path with `pytest.raises(SystemExit)`.

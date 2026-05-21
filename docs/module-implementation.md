# Writing Modules

This document explains how to implement a module for `rtl-comrade`.

For harness internals behind module instantiation and output analysis, see:

- [docs/harness/node.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/node.md)
- [docs/harness/structure.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/structure.md)
- [docs/harness/api.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/api.md)

## What A Module Is

A module is the node-local work unit in the graph.

The contract decides when the node runs and which inputs are supplied. The module defines what happens once that invocation occurs.

Examples:

- read a file and emit one line at a time
- add two numbers
- perform an ALU operation based on an opcode

That means business logic belongs in modules, not scheduling logic.

## Required Interface

A module is a plain Python class discovered from a plugin file.

At minimum:

- it must expose `run(...)`

The harness infers the module input surface from the `run(...)` signature.

Optionally:

- it may expose `finalise()` — a teardown hook called once after all `run(...)` invocations have completed and before `EndSentinel` is propagated downstream

## How The Harness Instantiates A Module

`Node` inspects the module constructor and only injects arguments that the constructor explicitly accepts.

Possible injected arguments are:

- `config`
- `id`

### `config`

If module `__init__` accepts `config`, the harness passes the graph node's `config` mapping.

If the module defines a nested `Config` class, the harness deserializes that mapping through `serde.from_dict(...)` before construction.

### `id`

If module `__init__` accepts `id`, the harness passes:

```python
"<node-id>.module"
```

This is mainly useful for logging or module-local tracing.

### No injected ports

Modules do not receive port objects directly.

The contract handles port consumption and returns one invocation's input bundle. The harness unwraps those payloads and calls the module with plain keyword arguments.

## The `run(...)` Signature Defines Inputs

Each `run(...)` parameter becomes one input port.

For example:

```python
class AddMod:
    def run(self, a: int, b: int):
        return int(a) + int(b)
```

This creates two input ports:

- `a`
- `b`

The current implementation preserves declaration order, and destination edges may refer to module inputs either by:

- string name
- 1-based positional index

That means changing parameter order is a graph-facing API change.

## Default Input Values

If a `run(...)` parameter has a Python default value, that input port becomes default-capable.

Example:

```python
class ExampleMod:
    def run(self, a, b=0):
        return a + b
```

Here:

- `a` is a required input
- `b` has a default value available to contracts

The built-in default contract can use such defaults without any upstream edge for that port.

## Allowed `run(...)` Forms

The harness supports several output styles.

### Plain return

Returning a non-`None` non-tuple value emits on the `"default"` output port.

```python
class AddMod:
    def run(self, a, b):
        return int(a) + int(b)
```

### Named-port return

Returning `(port_name, value)` emits on that named port.

```python
class SplitMod:
    def run(self, a):
        if a > 0:
            return ("positive", a)
        return ("non_positive", a)
```

### Generator

Yielding results emits multiple outputs across one invocation.

```python
class FileReadMod:
    def run(self):
        with open("input.txt", "r") as f:
            for line in f:
                yield line
```

### Async return

`run(...)` may be async and return one final result.

### Async generator

`run(...)` may also be an async generator and yield multiple results over time.

## Output Rules

The harness normalizes module outputs with these rules:

- `None` emits nothing
- non-tuple non-`None` values emit on `"default"`
- tuples must be exactly `(port_name, value)`
- `port_name` must be a string

If a tuple has the wrong length or a non-string port name at runtime, the harness logs an error and drops that malformed output.

## Static Output-Port Inference

`ModuleStructure` statically inspects the `run(...)` AST to infer known output ports.

This affects graph validation, so module authors need to know the rules.

### What the analyzer recognizes

- a non-`None` non-tuple `return` or `yield` implies the `"default"` port
- a tuple `return` or `yield` with a static string first element contributes that named port

### What weakens validation

If the first tuple element is dynamic rather than a static string literal, the runtime still allows it, but validation becomes weaker because the harness can no longer prove the full emitted-port set.

Example:

```python
class DynamicPortMod:
    def run(self, port_name, value):
        return (port_name, value)
```

This is allowed, but `definite_emits` becomes false.

### Nested helper functions are excluded

The analyzer intentionally ignores `return` and `yield` inside nested function bodies. It only treats top-level `run(...)` behavior as authoritative for output-port inference.

## The `finalise()` Hook

If a module defines `finalise()`, the harness calls it once after the last `run(...)` invocation and before sending `EndSentinel` downstream.

Both sync and async forms are accepted:

```python
class StatefulMod:
    def __init__(self):
        self._results = []

    def run(self, value):
        self._results.append(value)

    def finalise(self):
        print(f"collected {len(self._results)} values")
```

```python
class AsyncStatefulMod:
    def __init__(self):
        self._results = []

    def run(self, value):
        self._results.append(value)

    async def finalise(self):
        await flush_to_database(self._results)
```

`finalise()` does not receive arguments. If it raises, the harness treats it as fatal (same as an unhandled exception in `run(...)`). It supports the same output forms as `run(...)`: plain return, named-port tuple, sync generator, async return, and async generator. Return `None` to emit nothing.

If the module does not define `finalise`, or if `finalise` is a non-callable attribute, the harness silently skips the step.

## Runtime Call Model

For each invocation:

1. the contract returns `dict[str, Payload]` or `EndSentinel`
2. the harness stops the node if it receives `EndSentinel`
3. otherwise, it unwraps the payload objects to raw values
4. it calls `module.run(**inputs)`
5. it forwards any emitted outputs downstream

After all invocations complete:

6. if `module.finalise` exists and is callable, the harness calls it once
7. `EndSentinel` is propagated to all downstream edges

Important consequences:

- modules receive raw values, not `Payload` wrappers
- modules do not directly control graph termination; contracts do
- `finalise()` is always called after the last `run(...)`, regardless of whether termination was triggered by `EndSentinel` from a contract or by a zero-input node running once

## Logging Guidance

Logging participates in harness failure semantics.

- `DEBUG`, `INFO`, and `WARNING` are normal observability levels
- `ERROR` allows best-effort continuation but causes a failing exit at the end
- `CRITICAL` exits immediately

For modules, this usually means:

- use `ERROR` for runtime problems where continuing the graph still makes sense
- use `CRITICAL` or fatal paths only for conditions that should abort execution immediately

The sample modules show both styles:

- [modules/funcs.py](/Users/daniellim/Documents/random/rtl-comrade/modules/funcs.py): `ALUMod` logs `ERROR` on invalid opcodes
- [modules/io.py](/Users/daniellim/Documents/random/rtl-comrade/modules/io.py): `FileReadMod` uses fatal logging for file-access failures

## Config-Bearing Module Example

The current file reader module shows the intended pattern:

```python
from serde import serde

class FileReadMod:
    @serde
    class Config:
        file: str

    def __init__(self, config):
        self.file = config.file

    def run(self):
        with open(self.file, "r") as f:
            for line in f:
                yield line
```

Key points:

- the module defines a nested `Config`
- `__init__` accepts `config`
- the harness deserializes node config before construction

## Minimal Stateless Module Example

```python
class AddMod:
    def run(self, a, b):
        return int(a) + int(b)
```

This is the simplest useful shape:

- no constructor
- two inferred inputs
- one default-port output

## Named-Port Module Example

```python
class CompareMod:
    def run(self, a, b):
        if a > b:
            return ("gt", a)
        elif a < b:
            return ("lt", a)
        else:
            return ("eq", a)
```

This is the clearest way to expose multiple statically known output ports.

## Manifest Registration

To expose a module plugin by name, add it to a plugin file and register it in a manifest.

Current example:

- [modules/io.py](/Users/daniellim/Documents/random/rtl-comrade/modules/io.py)
- [modules/funcs.py](/Users/daniellim/Documents/random/rtl-comrade/modules/funcs.py)
- [modules/config.yaml](/Users/daniellim/Documents/random/rtl-comrade/modules/config.yaml)

Example manifest entry:

```yaml
files:
- file: funcs.py
  plugins:
  - name: add
    class_name: AddMod
```

The graph can then refer to that module by its exported name:

```yaml
nodes:
- id: add
  module: add
```

## Testing

Modules can be tested in isolation using `run_module_scenario` from `rtl_comrade.testing`.

The harness drives the module's `run(...)` method directly, without a graph or contract. You supply a sequence of input dicts (one per invocation) and the expected emissions per port.

### Loading module classes

The `modules/` directory is a plugin directory, not a Python package. Load module classes with `importlib.util` to avoid name conflicts with the standard library (notably `io`):

```python
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("modules_funcs", Path(__file__).parent.parent / "funcs.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
AddMod = _mod.AddMod
```

### conftest setup

Place a `conftest.py` next to your test files to make the `logging_handler` fixture available:

```python
# modules/tests/conftest.py
from rtl_comrade.testing import logging_handler  # noqa: F401
```

### Basic example

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

### Generator module

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

### Named-port module

```python
async def test_router_positive():
    await run_module_scenario(
        SplitMod,
        input_sequence=[{"a": 5}],
        expected_emissions={"positive": [5]},
    )
```

### Multi-step sequence

Pass multiple dicts to drive several invocations. Emissions are accumulated across all steps in call order:

```python
async def test_add_multi_step():
    await run_module_scenario(
        AddMod,
        input_sequence=[{"a": 1, "b": 2}, {"a": 10, "b": 20}],
        expected_emissions={"default": [3, 30]},
    )
```

### Source modules

A module with no `run(...)` parameters is a source node. Pass a single empty dict. The harness runs it once and stops, matching the graph runtime:

```python
async def test_source_emits_once():
    await run_module_scenario(
        SourceMod,
        input_sequence=[{}],
        expected_emissions={"default": [99]},
    )
```

### Config-bearing modules

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

### Testing error paths

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

### Coverage Target

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

## Design Advice

- Keep scheduling logic in contracts, not in modules.
- Keep emitted port names static when you can; it improves graph validation.
- Treat `run(...)` parameter names and order as part of the graph-facing API.
- Be conservative with `None`; it means "emit nothing", not "emit a default-port null payload".
- If you change module input shape or output-port semantics, update any sample graph that depends on it.
- Use `finalise()` for work that must happen after all inputs are consumed — closing files, flushing buffers, emitting summary or aggregate outputs.

## Current Limitations To Keep In Mind

- output-port analysis is intentionally conservative
- dynamic port names are allowed, but they weaken static validation
- modules have no direct access to payload metadata such as source node id or sequence number
- modules receive plain values after contract selection, not transport-layer objects

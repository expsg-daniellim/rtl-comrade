# Writing Modules

This document explains how to implement a module for `rtl-comrade`.

For harness internals behind module instantiation and output analysis, see:

- [docs/harness/node.md](../harness/node.md)
- [docs/harness/structure.md](../harness/structure.md)
- [docs/harness/api.md](../harness/api.md)

For testing modules in isolation, see [testing.md](testing.md).

For available contracts to pair with your module, see [docs/contracts/index.md](../contracts/index.md).

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

### Avoiding builtin/keyword clashes

If a parameter would shadow a Python builtin or keyword (`list`, `type`, `id`, `class`, …), give it a single trailing underscore (`list_`). The harness exposes the input port under the underscore-dropped name, so the graph and CLI use the bare name while your code keeps the safe one:

```python
class RouteListModeMod:
    def run(self, suite_cfg, list_: bool = False):
        return ("list", suite_cfg) if list_ else ("run", suite_cfg)
```

Here the input port is `list` (so an edge writes `port: list` and a CLI edge writes `cli: list`), and the value arrives as the `list_` argument. Two parameters that collapse to the same external name (e.g. both `list` and `list_`) are a fatal error. Avoid `help_` — its `--help` collides with the auto-generated help flag.

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

## Variadic Inputs (`*args` / `**kwargs`)

A `run(...)` signature may use `*args` or `**kwargs`. This makes the module's input surface **non-definite**: the harness can no longer derive the port set from the signature alone.

```python
class MergeMod:
    def run(self, **kwargs):
        return sum(int(v) for v in kwargs.values())
```

Consequences for a non-definite-input module:

- the harness builds the port set from the **incoming edges** in the graph YAML, not from the `run(...)` signature — each edge destination port becomes an input the contract can read
- `*args` and `**kwargs` themselves are not turned into ports; only the edge destination names are
- the harness emits a `non_definite_inputs` warning for the node at load time
- destination-port validation is weaker, because the harness cannot prove the full input set; an unknown string destination port is accepted rather than rejected

Named parameters declared alongside the variadic one still behave normally:

```python
class MergeMod:
    def run(self, key, **kwargs):
        ...
```

Here `key` is a definite, signature-derived port; the extra ports arrive via edges and reach the module through `**kwargs`.

Keyword-only parameters (those after a bare `*`) do **not** make a module non-definite — they are ordinary ports, default-capable if they carry a Python default.

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

`ModuleStructure` statically inspects the `run(...)` AST — and the `finalise()` AST when one is defined — to infer known output ports. Emits from both methods are merged into the same port set.

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

`finalise()` does not receive arguments. If it raises, the harness treats it as fatal (same as an unhandled exception in `run(...)`) — but that is the fallback backstop, not a license to skip handling: `finalise()` owns its exceptions just as `run(...)` does (see [Exception Handling Is The Module's Responsibility](#exception-handling-is-the-modules-responsibility)). It supports the same output forms as `run(...)`: plain return, named-port tuple, sync generator, async return, and async generator. Return `None` to emit nothing. Ports emitted from `finalise()` are statically inferred alongside `run(...)`'s — see [Static Output-Port Inference](#static-output-port-inference).

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

- [modules/funcs.py](../../modules/funcs.py): `ALUMod` logs `ERROR` on invalid opcodes
- [modules/io.py](../../modules/io.py): `FileReadMod` uses fatal logging for file-access failures

## Exception Handling Is The Module's Responsibility

A module must catch **every** exception its own code can raise and translate it into the harness failure model. It must **not** let any exception bubble up to the harness.

This is exhaustive, not best-effort. Every call a module makes has a knowable, enumerable set of exceptions it can raise — file I/O (`FileNotFoundError`, `PermissionError`, `OSError`), subprocess launch (`FileNotFoundError` for a missing binary), parsing (`yaml.YAMLError`, `serde.SerdeError`), schema mismatches (`TypeError`, `KeyError`), arithmetic, indexing, and so on. Walk each line of `run(...)` and `finalise()`, list what it can raise, and handle all of it. There is no "unlikely enough to skip" and no "surprising at this layer": if a line can raise it, the module catches it. You can read the code, so nothing it can raise is unknown to you — every exception is the module's to handle.

Translate each caught exception into one of the sanctioned outcomes:

- `log.fatal(...)` / `CRITICAL` — an unrecoverable setup/config error that must abort the whole run immediately (see [modules/io.py](../../modules/io.py): `FileReadMod` catches every file-access error its `open` can raise and converts each to a `log.fatal`).
- `log.error(...)` / `ERROR` — a per-item failure where the graph should still complete the remaining work, then exit non-zero.
- a named output port — when the failure is ordinary business logic that routes the item off the main line (e.g. a "fail" branch carrying a result payload), rather than a logged severity.

In every case the exception is caught inside `run(...)` (or `finalise()`) and does not escape. Converting it to a structured log event keeps the operator-facing output domain-specific (a named event with fields) instead of a raw traceback, and preserves the deliberate severity choice that drives the exit code — see [the failure model](../harness/logging.md) and [docs/invariants.md](../invariants.md).

### The harness backstop is for defects, not for cases you skipped

The harness does catch an unhandled exception escaping `run(...)` or `finalise()` and treat it as fatal, but this is a last-resort safety net for genuine programming defects — a bug the author did not account for — **not** a runtime path to design against. An exception your code can raise is never "unforeseen"; it is unhandled, which is a gap to close. Reaching the backstop in normal operation means the module failed to handle something it plainly could have. Relying on it produces an unstructured traceback in place of a meaningful failure event and collapses the deferred-vs-immediate severity distinction (everything becomes an immediate abort).

### The one exception that should propagate

`asyncio.CancelledError` is a harness control signal, not a module error. In an async module, perform any necessary cleanup (closing files, reaping subprocesses) and then **re-raise** it so the harness can cancel the node cleanly. Do not swallow it and do not convert it to a log event.

## Config-Bearing Module Example

The current file reader module shows the intended pattern:

```python
from pathlib import Path
from serde import serde

class FileReadMod:
    @serde
    class Config:
        file: Path

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
- declaring a config field as `Path` (rather than `str`) enables the `{graph}` prefix in the graph YAML, which the harness resolves to the graph file's directory at construction time (see [docs/harness_configs/graph.md](../harness_configs/graph.md))

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

- [modules/io.py](../../modules/io.py)
- [modules/funcs.py](../../modules/funcs.py)
- [modules/config.yaml](../../modules/config.yaml)

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

## Cross-File Imports

A plugin file may import from sibling files. For sibling imports to resolve, the loader puts the right directory on `sys.path` — but it treats a folder as a package only when that folder contains an `__init__.py`. Add an empty `__init__.py` to any folder you want to import through:

- A plain folder (no `__init__.py`) is put on `sys.path` directly, so `import sibling` works but `from folder.sibling import X` does not.
- A package folder (with `__init__.py`) has its parent put on `sys.path` instead, so absolute imports like `from modules.rtl_buddy.schema import X` resolve. The loader walks the whole `__init__.py` chain, so every folder in a multi-level package (e.g. both `modules/` and `modules/rtl_buddy/`) needs its own `__init__.py`; a gap anywhere in the chain stops the walk and the absolute import fails.

See [docs/harness/loader_utils.md](../harness/loader_utils.md) for the exact `sys.path` rule.

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
- variadic inputs (`*args`/`**kwargs`) make the input set non-definite, so ports come from edges and destination-port validation is weaker
- modules have no direct access to payload metadata such as source node id or sequence number
- modules receive plain values after contract selection, not transport-layer objects

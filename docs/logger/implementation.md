# Writing Logging Plugins

This document explains how to implement a custom logging plugin for `rtl-comrade`.

A logging plugin is referenced from a graph's `logging` block and customises how that graph's log events are filtered, transformed, and rendered.

For the harness internals behind logging plugins, see:

- [docs/harness/logging.md](../harness/logging.md) — the processor/handler model, `include_default`, the harness `LoggingFatalHandler`, and the two hard constraints
- [docs/harness/loader_logger.md](../harness/loader_logger.md) — `LoggingConfig.load`: how each entry is imported, classified, and signature-validated
- [docs/harness/app.md](../harness/app.md) — `App.setup_logging`: where resolved plugins are constructed and installed

For the YAML schema of the `logging` block, see [docs/harness_configs/graph.md](../harness_configs/graph.md).

For a worked example of a stateful processor (accumulate in `__call__`, flush in `finalise()`), see [summary-processor.md](summary-processor.md).

## What A Logging Plugin Is

A logging plugin is a per-graph customisation of harness logging. The harness already installs its own root handler (`LoggingFatalHandler`) with a terminal `ConsoleRenderer`; a logging plugin extends or replaces parts of that pipeline for one graph run.

Each entry in a graph's `logging.handlers` list resolves to exactly one of two kinds:

- a **structlog processor** — a callable `(logger, method_name, event_dict)` that filters or transforms the event dict (and may suppress it). Processors join the harness handler's formatter chain.
- a **`logging.Handler`** — a full stdlib handler appended to the root logger alongside the harness handler.

The harness decides which kind an entry is by inspecting the resolved object, not by any declaration in the YAML: a `logging.Handler` subclass becomes a handler, and anything else callable becomes a processor.

Scheduling and computation belong to contracts and modules. A logging plugin only observes, transforms, and renders log events; it must not drive graph behaviour.

## Where Logging Plugins Are Configured

Logging plugins are listed under a graph YAML file's `logging` block, not in a plugin manifest:

```yaml
logging:
  include_default: true       # optional, defaults to true
  handlers:
  - path: log/plugins.py       # plugin file, relative to the graph file's directory
    name: add_tag              # the exported callable/class to select from that file
    config:                    # optional, only consumed by config-bearing classes
      key: value
```

Two things distinguish this from module/contract loading:

- `name` is the **actual attribute name** defined in the file at `path` (a function, class, or module-level instance), not a manifest alias. There is no `config.yaml` manifest for logging plugins.
- Resolution is **lazy and per-run**: the `logging` block is resolved when the subcommand runs (in the `Graph.construct_run` closure, after graph construction, before any node executes), so a malformed logging config is reported at run time and applies to that single run only.

`config` is only meaningful for a class whose `__init__` declares a `config` parameter — see [How The Harness Constructs A Plugin](#how-the-harness-constructs-a-plugin).

## Processors

A processor is the common case. It is a structlog `Processor`: a callable taking `(logger, method_name, event_dict)` and returning a transformed event dict (or, when terminal, a rendered string).

```python
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping

def add_tag(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    event_dict['tag'] = 'INJECTED'
    return event_dict
```

Processors join the harness handler's `ProcessorFormatter` chain **in list order**, ahead of the terminal renderer.

### Signature validation is strict and fatal

Unlike modules and contracts — where the harness infers the input surface and tolerates loose shapes — every processor's signature is validated against structlog's `Processor` shape, and a mismatch is **fatal** (it stops the run before any node executes). The rules are:

- **arity**: exactly three positional parameters. For a processor *class*, validation runs on `__call__` with `self` dropped; for a function or instance it runs on the callable directly. Constructor parameters such as `config` are not counted.
- **parameter 1 (`logger`)**: must be unannotated or annotated `Any`. structlog passes a wrapped logger here and the type is deliberately unconstrained.
- **parameter 2 (`method_name`)**: must be annotated exactly `str`.
- **parameter 3 (`event_dict`)**: must be annotated as an *EventDict* — a bare `dict` or `MutableMapping`, or either parameterised as `[str, Any]` (e.g. `dict[str, Any]`, `MutableMapping[str, Any]`).
- **return annotation**: depends on whether this processor is terminal (see [`include_default`](#include_default-and-the-terminal-renderer)). A non-terminal processor must return an EventDict; the terminal processor must return `str`.

Annotations are resolved with `eval_str`, so plugin files should use `from __future__ import annotations` and import the annotation types they reference. An annotation that cannot be resolved is fatal (`signature.unresolved_annotation`).

### Suppressing events with `DropEvent`

A processor signals "drop this event" by raising `structlog.exceptions.DropEvent`:

```python
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping
from structlog.exceptions import DropEvent

def only_errors(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    if event_dict.get('level') not in ('error', 'critical'):
        raise DropEvent
    return event_dict
```

When a processor raises `DropEvent`, the event reaches neither the terminal renderer nor any later processor in the chain, and the harness handler drops the record silently rather than surfacing a logging error. Dropping output does **not** affect failure tracking: an `ERROR` event still flips the failure flag and a `CRITICAL` event still exits, because that bookkeeping lives on the harness handler outside the formatter chain (see [logging.md](../harness/logging.md)).

### End-of-run finalisation with `finalise()`

A processor may expose a `finalise()` method (no arguments). At the end of a run, `App.cleanup` finalises the run's processors (then its handlers) and calls `finalise()` on every one that defines it — use it for a processor that accumulates state across the run, such as one that counts events in `__call__` and writes a summary at the end. It is duck-typed: a processor whose `finalise` is missing or not callable is skipped, so the method is optional. The same end-of-run timing limits apply as for handlers — see *End-of-run finalisation* under [Handlers](#handlers) below.

Unlike a handler, a processor has no `emit`; it observes each event through its `__call__` (returning the event dict so the chain continues) and flushes in `finalise`.

```python
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping

class EventCounter:
    def __init__(self):
        self.count = 0

    def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        self.count += 1
        return event_dict

    def finalise(self):
        print(f"saw {self.count} events")

counter = EventCounter()   # reference `name: counter` from the graph YAML
```

## Handlers

A handler entry is a full `logging.Handler` subclass, appended to the root logger:

```python
import logging

class CaptureHandler(logging.Handler):
    def emit(self, record):
        # record.msg is the raw structlog event dict, not a pre-rendered string
        archive(record.msg)
```

Handlers are not signature-validated; they only need to subclass `logging.Handler`. They are installed alongside — not inside — the harness handler, so two structural constraints apply. Both are load-bearing; design around them.

### A handler never observes `CRITICAL` records

A handler is appended to the root logger **after** the harness `LoggingFatalHandler`. Root handlers fire in add-order, and the harness handler raises `typer.Exit(1)` on any `CRITICAL` record before control reaches a later-added handler. A custom handler therefore sees `DEBUG` through `ERROR` records but **never** a `CRITICAL` one. Do not write a handler whose job is to flush or react to fatal records — by the time a fatal record exists the process is already exiting and the handler is downstream of that exit.

### A handler inherits only the shared preprocessors

A handler is a separate `logging.Handler`, not a processor in the harness handler's chain. It inherits **only** the shared preprocessor pre-chain (`initialise_logging`'s contextvars merge, log level, logger name, timestamp). It does **not** inherit the harness handler's `ProcessorFormatter`, its `ConsoleRenderer`, the `include_default`/terminal-renderer logic, or the `DropEvent` catch.

In particular, without its own formatter a handler receives the **raw event `dict`** as `record.msg`. So a handler author must either:

- attach a `structlog.stdlib.ProcessorFormatter` (with `foreign_pre_chain` and a terminal renderer) to the handler to get formatted output, or
- read `record.msg` directly as the event dict and format it themselves.

A handler that assumes a pre-rendered string will instead get `str(dict)`.

### End-of-run finalisation with `finalise()`

A handler may expose a `finalise()` method (no arguments). At the end of a run, `App.cleanup` walks the root logger's handlers and calls `finalise()` on every handler that defines one — use it to flush buffers, close files, or write a summary. It is duck-typed: a handler whose `finalise` is missing or not callable is skipped, so the method is optional.

```python
import logging

class CaptureHandler(logging.Handler):
    def emit(self, record):
        archive(record.msg)

    def finalise(self):
        flush_archive()
```

Two limits follow from where `cleanup` runs:

- `finalise()` runs **before** the run's failure check, so it is called whether the run passed or failed (deferred `ERROR`). It is **not** called on a `CRITICAL`-triggered exit, because the harness handler raises `typer.Exit(1)` before `cleanup` is reached — the same reason a handler never observes a `CRITICAL` record (see above). Do not rely on `finalise()` for fatal-path cleanup.
- It is a per-run hook on a per-run handler: the handler is constructed for that graph run and finalised at its end. See [docs/harness/app.md](../harness/app.md) for the `cleanup` lifecycle.

## How The Harness Constructs A Plugin

After classification, each plugin is constructed at install time (`LoggingPlugin.construct`, called from `App.setup_logging`). Construction depends on whether the resolved object is a class:

- a **function** or an already-built **instance** is used **as-is** — it is never re-constructed, and supplying `config` for one is a mistake the harness warns about (`config.mismatch`).
- a **class** (whether a processor class or a `logging.Handler` subclass) is **instantiated**, mirroring how modules and contracts are constructed from their classes.

### `config`

When the plugin is a class, the harness inspects its `__init__`:

- if `__init__` accepts a `config` parameter and the class defines a nested `Config` type, the `config` dict from the YAML is deserialised through `serde.from_dict(...)` and passed as `config=`;
- if `__init__` accepts `config` but the class has no nested `Config`, the raw dict is passed and the harness warns (`config.mismatch`);
- if `__init__` does not accept `config`, the class is constructed with no arguments.

This is the same pattern as module/contract `Config` injection. A `Config` field declared as `Path` (rather than `str`) supports the `{graph}` prefix, which the harness resolves to the graph file's directory at construction time.

```python
import logging
from pathlib import Path
from dataclasses import dataclass
from serde import serde

class FileHandler(logging.Handler):
    @serde
    @dataclass
    class Config:
        out: Path                 # `{graph}/run.log` resolves to <graph dir>/run.log

    def __init__(self, config):
        super().__init__()
        self.out = config.out

    def emit(self, record):
        ...
```

A construction failure is fatal (`init`); a `typer.Exit` raised by the plugin during construction propagates unchanged.

## `include_default` And The Terminal Renderer

`include_default` (default `true`) controls the harness handler's terminal renderer and therefore what return type processors must have:

- **`true`**: the harness handler's `ConsoleRenderer` stays terminal. All configured processors are non-terminal and must return an EventDict; they run before `ConsoleRenderer`.
- **`false`**: `ConsoleRenderer` is dropped, and the **last** configured processor becomes the terminal renderer — it must return `str`, while all earlier processors return an EventDict. With no processors at all, the harness handler renders nothing; if there are also no handler entries, the loader warns `no_renderers` (nothing renders anything).

A terminal renderer under `include_default: false` looks like:

```python
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping

def render(logger, method_name: str, event_dict: MutableMapping[str, Any]) -> str:
    return f"{event_dict.get('timestamp', '')} {event_dict.get('event')}"
```

Whatever `include_default` is, failure and exit tracking on the harness handler are unaffected.

## Plugin Forms At A Glance

| Resolved object | Classified as | Constructed? | Config-bearing? | Signature-validated? |
|---|---|---|---|---|
| `logging.Handler` subclass | handler | yes | yes (via `Config`) | no |
| processor class (defines `__call__`) | processor | yes | yes (via `Config`) | yes (on `__call__`, `self` dropped) |
| processor function | processor | no (used as-is) | no | yes |
| processor instance (module-level) | processor | no (used as-is) | no | yes (on bound `__call__`) |

Anything that is neither a `logging.Handler` subclass nor callable is fatal (`invalid_logging_handler`).

## Examples

### A processor instance

A module-level instance is used as-is; configure it in Python at definition time rather than through `config`:

```python
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping

class KeyRenamer:
    def __init__(self, mapping):
        self.mapping = mapping

    def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        for src, dst in self.mapping.items():
            if src in event_dict:
                event_dict[dst] = event_dict.pop(src)
        return event_dict

rename = KeyRenamer({'event': 'message'})   # reference `name: rename` from the graph YAML
```

### A processor class with config

```python
from __future__ import annotations
from typing import Any
from collections.abc import MutableMapping
from dataclasses import dataclass
from serde import serde

class Tagger:
    @serde
    @dataclass
    class Config:
        tag: str

    def __init__(self, config):
        self.tag = config.tag

    def __call__(self, logger, method_name: str, event_dict: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
        event_dict['tag'] = self.tag
        return event_dict
```

```yaml
logging:
  handlers:
  - path: log/plugins.py
    name: Tagger
    config:
      tag: nightly-run
```

## Design Advice

- Keep logging plugins observational. They render, filter, and route; they must not influence graph scheduling or results.
- Prefer a **processor** for transforming or filtering events in the harness pipeline; use a **handler** only when you need an independent sink (a file, a network target, an in-memory archive).
- Use `DropEvent` to filter, not exceptions; a raised exception other than `DropEvent`/`typer.Exit` escalates through the harness fatal path.
- Mind the return-type contract: every non-terminal processor returns an EventDict; only the terminal renderer (under `include_default: false`) returns `str`.
- Do not rely on a handler seeing `CRITICAL` records, and do not assume a handler receives pre-rendered text — attach a `ProcessorFormatter` or read `record.msg` as the event dict.
- Declare config paths as `Path` to get `{graph}`-relative resolution, the same as modules and contracts.

## Current Limitations To Keep In Mind

- logging plugins are referenced directly by `path`/`name`; there is no manifest, so a file's exported attribute name *is* its plugin name.
- processor signature validation is strict — annotations must be present (where required) and resolvable, otherwise the run fails before it starts.
- handlers are second-class to the harness handler: they never see `CRITICAL` and inherit only the shared preprocessors.
- custom logging is resolved per run and applies to that run only; it cannot reconfigure logging at startup or across graphs.

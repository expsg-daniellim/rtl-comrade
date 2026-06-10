# `logging.py`

Source: [src/rtl_comrade/logging.py](../../src/rtl_comrade/logging.py)

## Role

This file configures harness logging and encodes the current failure semantics attached to log levels.

## See Also

- [README.md](README.md)
- [__main__.md](__main__.md)
- [app.md](app.md) — `App.setup_logging` lifecycle and the `run`-closure install point
- [graph.md](graph.md)
- [node.md](node.md)
- [loader_logger.md](loader_logger.md) — `LoggingConfig.load` resolution and processor-signature validation
- [docs/harness_configs/graph.md](../harness_configs/graph.md) — the `logging` config schema
- [docs/logger/implementation.md](../logger/implementation.md) — how to write a custom logging plugin (processor or handler)

## Main Responsibilities

- initialize `structlog`
- install a root logging handler
- track whether the run emitted any error-level records
- force immediate process termination on critical logs

## Place In The System

This is the harness observability and failure-policy layer. Logging is intentionally part of runtime control: the harness uses log levels to record operator-facing information and to drive run failure behavior.

## Important Behaviors

- `initialise_logging(...)` clears existing root handlers and installs `LoggingFatalHandler`
- `DEBUG`, `INFO`, and `WARNING` behave as normal logging levels
- `ERROR` sets `handler.failure = True`
- `CRITICAL` raises `typer.Exit(1)` immediately
- `main()` checks `handler.failure` to decide its final exit code
- harness sites that catch non-`rtl_comrade` exceptions now attach `exc_info=e` so the original traceback is preserved in the log event
- changing a log level can therefore change both what operators see and how the harness reports success or failure

## The `render` Flag and `DropEvent`

`LoggingFatalHandler` carries a mutable `render` flag (default `True`). It gates only the write path: when `render` is `False`, `emit` skips `super().emit(record)` entirely and writes nothing, but it still updates `failure` and still raises `typer.Exit(1)` on `CRITICAL`. Failure and exit tracking therefore run regardless of whether anything is rendered.

`render` exists so per-graph custom logging can suppress the harness handler's own output (see below). Per-graph setup flips it from `App.setup_logging`: it becomes `False` exactly when the resolved processor chain is empty, meaning the harness handler has no terminal renderer to run and so writes nothing.

When `render` is `True`, `emit` wraps `super().emit(record)` in a `try`/`except DropEvent`. A structlog processor in the formatter chain signals "suppress this event" by raising `structlog.exceptions.DropEvent`. `Formatter.format()` runs the chain and can raise it before any byte is written, so the handler catches it and drops the record silently rather than letting it surface as a logging error. The catch is on the write path only; failure and exit tracking below it still run.

## Per-Graph Custom Logging

`GraphConfig` carries a `logging` block ([config schema](../harness_configs/graph.md)) holding a **list** of custom handlers plus the top-level `include_default` bool. Each list entry resolves to one of two things:

- a **structlog processor** — a callable matching structlog's `Processor` shape `(logger, method_name, event_dict)`, which filters or transforms the event dict and may raise `DropEvent` to suppress the event. Processors join the harness handler's formatter chain.
- a full **`logging.Handler`** — constructed and appended to the root logger alongside the harness handler.

`LoggingConfig.load` (in [loader_logger.md](loader_logger.md)) imports and selects each named object, classifies it by whether it is a `logging.Handler` subclass, validates every processor's signature, and returns the `(processors, handlers)` pair — where the processor and handler entries are *unconstructed specs*, not instances; the consumer reads `include_default` from the config separately. Construction (instantiating a class, deserialising its `Config`, relativising `{graph}` paths) is `LoggingPlugin.construct`, invoked by the consumer `App.setup_logging` at install time — mirroring how the loader returns module/contract **classes** that `node.py` constructs, rather than instantiating during resolution. Resolution and construction happen **lazily at graph invocation** — in the `run` closure after `Graph.from_config`, before any node runs — so custom logging applies to that run only.

### `include_default` and the terminal renderer

`include_default` controls the harness handler's terminal renderer:

- `true` (default): the harness handler's `ConsoleRenderer` is the terminal processor. Any configured processors are non-terminal and must return an event dict (`-> EventDict`); they run before `ConsoleRenderer`.
- `false`: `ConsoleRenderer` is dropped. The **last configured processor replaces it as the terminal renderer** and must therefore return `str` (`-> str`); all earlier processors return an event dict. If there are no processors at all, the harness handler renders nothing (its `render` flag goes `False`), and the loader warns `no_renderers` when there are also no Handler-type entries — i.e. nothing renders anything.

Whichever case applies, failure and exit tracking on the harness handler are unaffected.

## Constraint: custom handlers never observe `CRITICAL` records

A Handler-type entry is appended to the root logger **after** the harness `LoggingFatalHandler`. Root handlers fire in add-order via `logging.Logger.callHandlers`, so the harness handler runs first on every record. On a `CRITICAL` record its `emit` raises `typer.Exit(1)`, and that exception propagates out of `callHandlers` before any later-added handler is reached.

The consequence is structural, not incidental: a custom `logging.Handler` will see `DEBUG` through `ERROR` records but will **never** see a `CRITICAL` record. Do not design a custom handler whose job is to observe, flush, or react to fatal records — by the time a fatal record exists, the process is already exiting and your handler is downstream of the exit. If you need fatal-record behavior, it belongs in the harness handler, not a custom one.

## Constraint: a wholly-custom `logging.Handler` inherits only the shared preprocessors

A Handler-type entry is a complete `logging.Handler`, not a processor in the harness handler's chain. It inherits **only** the shared `preprocessors` chain (the foreign pre-chain set up by `initialise_logging`: contextvars merge, log level, logger name, timestamp). It does **not** inherit the harness handler's `ProcessorFormatter`, its `ConsoleRenderer`, the `include_default`/terminal-renderer logic, or the `DropEvent` catch. None of that applies to a separate handler.

In particular, without its own formatter a custom handler receives the **raw event `dict`** as `record.msg`: structlog hands the event dict to stdlib logging, and a default `logging.Formatter` renders it as `str(dict)`. So an author writing a custom handler must either:

- attach a `structlog.stdlib.ProcessorFormatter` (with `foreign_pre_chain` and a terminal renderer) to the handler to get formatted output, or
- read `record.msg` directly as the event dict and format it themselves.

A custom handler that assumes it will receive a pre-rendered string will instead get `str(dict)`.

## Failure Model

The harness intentionally distinguishes between non-fatal and fatal failures:

- `ERROR` means the run has failed, but execution is allowed to continue
- `CRITICAL` means the run must terminate immediately

The purpose of `ERROR` is to support best-effort completion. If some work has already started, the graph can continue processing and avoid wasting partially completed work, while still returning a failing exit status at the end.

In effect:

- `DEBUG`, `INFO`, and `WARNING` are normal observability signals
- `ERROR` is deferred failure
- `CRITICAL` is immediate failure

## Architectural Implication

Logging in this system is not just an observability side channel. It is part of the harness contract for signaling failure severity.

- adding a new `log.error(...)` site is a semantic change to deferred failure behavior
- promoting a message from `WARNING` to `ERROR` changes exit semantics
- promoting a message to `CRITICAL` can change termination timing

That design is intentional and should be preserved unless the project explicitly chooses a different failure model.

## Exception Logging

The harness distinguishes between two broad categories of logged exceptions:

- non-`rtl_comrade` exceptions such as reflection errors, import errors, YAML parse errors, and plugin-construction failures are logged with `exc_info=e`
- project-local semantic exceptions may instead log structured fields extracted from the exception object when the event itself already identifies the failure mode

The intent is that external or unexpected failures keep their traceback in logs, while harness-defined control-path failures can remain compact and domain-specific when the traceback adds little value.

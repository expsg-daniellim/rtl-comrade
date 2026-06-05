# `logging.py`

Source: [src/rtl_comrade/logging.py](../../src/rtl_comrade/logging.py)

## Role

This file configures harness logging and encodes the current failure semantics attached to log levels.

## See Also

- [README.md](README.md)
- [__main__.md](__main__.md)
- [graph.md](graph.md)
- [node.md](node.md)

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

# `app.py`

Source: [src/rtl_comrade/app.py](../../src/rtl_comrade/app.py)

## Role

Owns the full CLI lifecycle: config-file discovery, logging setup, subcommand registration, and graph execution. `__main__.py` is just a thin wrapper around this class.

## See Also

- [__main__.md](__main__.md)
- [graph.md](graph.md)
- [logging.md](logging.md)

## Main Responsibilities

- search the directory tree from cwd for the config file
- set up structured logging from the `--level` flag
- pre-load each command's `GraphConfig` at startup
- register each configured command as a typer subcommand
- map CLI exceptions and harness failures to process exit codes

## Place In The System

`app.py` is the CLI entry point; `__main__.py` is a thin wrapper around it. It bridges config discovery, logging initialisation, plugin loading, and graph execution into a single startup sequence. Subcommand dispatch is handled by typer.

## Key Behaviors

- graph configs are loaded eagerly at startup, not lazily on first invocation, so malformed graphs are rejected before any subcommand runs
- a preliminary `parse_known_args` pass extracts `--config-file` and `--level` before typer is initialised; the pass is intentionally silent and does not reject unknown arguments
- the directory where the config file was found is stored on `RtlComradeConfig.relative_path`; graph paths are resolved relative to that directory at subcommand registration time
- if the loaded `GraphConfig` has a non-empty `sig`, `no_args_is_help=True` is set on the subcommand automatically

## Config File — `rtl_comrade_config.yaml`

The CLI is driven by a YAML config file that maps subcommand names to graph paths:

```yaml
commands:
  alu:
    path: "graphs/graph.yaml"
  add:
    path: "graphs/graph2.yaml"
    help: "optional help string"
```

`App` searches for this file by ascending the directory tree from the current working directory, stopping at the git repository root (a directory containing `.git/`) or the filesystem root. The file name searched for defaults to `rtl_comrade_config.yaml` and can be changed with `--config-file`. This is a filename, not a path — the directory tree search still runs from the current working directory regardless.

The config is parsed into `RtlComradeConfig` and `CommandConfig` via `pyserde`. The directory in which the file was found is stored on `RtlComradeConfig.relative_path` and used to resolve graph paths at subcommand registration time.

## Two-Pass Argument Parsing

`App.__init__` uses `argparse` with `parse_known_args` for a lightweight preliminary pass to extract `--config-file` and `--level` before typer is initialized. This lets logging and config discovery happen before the typer app is constructed.

The same options are re-declared as typer parameters on the `main` callback so they appear correctly in `--help` output. The argparse pass is intentionally silent — it does not validate or reject unknown arguments.

## Subcommand Registration

Each entry in `config.commands` becomes a typer subcommand. During `App.__init__`, the graph config for each command is loaded via `GraphConfig.from_file`. The graph path in each command is resolved relative to the directory containing the config file (`config.relative_path / command.path`), not relative to the runner's working directory. Loading errors (file not found, invalid YAML, schema errors, invalid unicode, invalid CLI parameter names) are caught and logged as fatal, aborting startup.

The loaded `GraphConfig`'s `sig` field — an `inspect.Signature` built from the graph's CLI edges — drives the subcommand's parameter list. If the signature is non-empty, `no_args_is_help=True` is set automatically so the subcommand prints help when invoked with no arguments.

## Logging Level

The `--level` option accepts any standard Python logging level name (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`), case-insensitive. It is forwarded to `initialise_logging` at startup.

## Error Handling

`App.run()` catches all typer and click exception types and maps them to exit codes:

| Exception | Behavior |
|---|---|
| `NoArgsIsHelpError` | exits 0 (help shown) |
| `typer.Exit` | exits with `e.code` |
| `typer.Abort` | exits 1 |
| `click.MissingParameter` | logs `usage_error`, exits with click's code |
| `click.BadParameter` | logs `usage_error`, exits with click's code |
| `click.BadOptionUsage` | logs `usage_error`, exits with click's code |
| `click.UsageError` | logs `usage_error`, exits with click's code |

## Graph Execution

Each subcommand is driven by a closure returned by `Graph.construct_run(config, setup_logging, cleanup)`. When the subcommand is invoked, the closure:

1. constructs the runtime `Graph` from the pre-loaded `GraphConfig` via `Graph.from_config`
2. resolves the graph's custom logging via `config.logging.load(config.relative_path)` and installs it via `setup_logging(processors, handlers, config.logging.include_default)`
3. injects the resolved CLI argument values into the graph's CLI nodes
4. runs the graph via `asyncio.run`
5. calls `cleanup()`, which finalises the run's processors and the root logger's handlers then raises `typer.Exit(1)` if `self.handler.failure` is set

This converts deferred `ERROR`-level log failures into a non-zero process exit code.

`cleanup` first walks the run's processors (`self.processors`, stored by `setup_logging`) and then `self.root_logger.handlers`, calling a `finalise()` method on every plugin that defines one (duck-typed via `getattr`; a plugin whose `finalise` is missing or not callable is skipped). This runs **before** the `failure` check so plugins flush even on a failing run. Because a `CRITICAL` record exits via the harness handler before `cleanup` is reached, the finalise pass runs on normal completion and on deferred-`ERROR` exits, but not on a `CRITICAL`-triggered exit. A processor or handler plugin needing an end-of-run flush or close should expose `finalise()`; see [docs/logger/implementation.md](../logger/implementation.md).

## Logging Lifecycle

Logging is installed in two stages.

At startup, `App.__init__` calls `initialise_logging(level)` once, which installs the harness `LoggingFatalHandler` on the root logger and returns the handler and the root logger. `App` keeps both (`self.handler`, `self.root_logger`) so it can amend the configuration per graph later. The shared preprocessor chain is read back from `structlog.get_config()["processors"]` when needed, rather than cached on `App`.

Per-graph custom logging is resolved and installed **lazily at graph invocation**, not at startup, mirroring how modules and contracts load at run time. Inside the `run` closure — after `Graph.from_config`, before any node executes — `config.logging.load(config.relative_path)` resolves the graph's `logging` config into the `(processors, handlers)` pair, where `processors`/`handlers` are *unconstructed* specs (the loader imports and classifies but does not instantiate, mirroring how the loader returns module/contract classes for `node.py` to construct). The closure reads `include_default` from `config.logging` and calls `App.setup_logging(processors, handlers, include_default)`, which:

- constructs each spec via `spec.construct()` (`LoggingPlugin.construct` — instantiating a class, deserialising its `Config` and relativising `{graph}` paths, or using a function/instance as-is) and appends the terminal `ConsoleRenderer` when `include_default`, keeping the resulting chain on `self.processors` for end-of-run finalisation (the `ConsoleRenderer` has no `finalise` and is skipped there);
- sets `self.handler.render` to `bool(chain)`, so the harness handler writes nothing when there is no terminal renderer;
- rebuilds the harness handler's `ProcessorFormatter` from the constructed chain (with the foreign pre-chain read from `structlog.get_config()["processors"][:-1]`) when the chain is non-empty;
- constructs and appends each Handler-type spec to the root logger.

Because resolution happens in the `run` closure, custom logging applies to that single graph run only, and a malformed logging config is reported when the subcommand runs rather than at startup. See [logging.md](logging.md) for the processor/handler model and its two hard constraints, and [loader_logger.md](loader_logger.md) for `LoggingConfig.load` itself.

## Caveats

- `--config-file` is a filename, not a path; tree ascent always starts from the current working directory regardless of the value supplied
- the preliminary argparse pass and the typer app both declare `--config-file` and `--level`; they must be kept in sync manually

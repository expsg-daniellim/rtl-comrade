# `app.py`

Source: [src/rtl_comrade/app.py](../../src/rtl_comrade/app.py)

## Role

Owns the full CLI lifecycle: config-file discovery, logging setup, subcommand registration, and graph execution. `__main__.py` is just a thin wrapper around this class.

## See Also

- [__main__.md](__main__.md)
- [graph.md](graph.md)
- [logging.md](logging.md)

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

The config is parsed into `RtlComradeConfig` and `CommandConfig` via `pyserde`.

## Two-Pass Argument Parsing

`App.__init__` uses `argparse` with `parse_known_args` for a lightweight preliminary pass to extract `--config-file` and `--level` before typer is initialized. This lets logging and config discovery happen before the typer app is constructed.

The same options are re-declared as typer parameters on the `main` callback so they appear correctly in `--help` output. The argparse pass is intentionally silent — it does not validate or reject unknown arguments.

## Subcommand Registration

Each entry in `config.commands` becomes a typer subcommand. During `App.__init__`, the graph config for each command is loaded via `GraphConfig.from_file`. Loading errors (file not found, invalid YAML, schema errors, invalid unicode, invalid CLI parameter names) are caught and logged as fatal, aborting startup.

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

Each subcommand is driven by a closure returned by `Graph.construct_run(config, cleanup)`. When the subcommand is invoked, the closure:

1. constructs the runtime `Graph` from the pre-loaded `GraphConfig` via `Graph.from_config`
2. injects the resolved CLI argument values into the graph's CLI nodes
3. runs the graph via `asyncio.run`
4. calls `cleanup()`, which raises `typer.Exit(1)` if `self.handler.failure` is set

This converts deferred `ERROR`-level log failures into a non-zero process exit code.

## Known Gaps

- Graph paths in the config are resolved relative to the runner's working directory, not relative to the config file's location.

# `app.py`

Source: [src/rtl_comrade/app.py](/Users/daniellim/Documents/random/rtl-comrade/src/rtl_comrade/app.py)

## Role

Owns the full CLI lifecycle: config-file discovery, logging setup, subcommand registration, and graph execution. `__main__.py` is just a thin wrapper around this class.

## See Also

- [__main__.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/__main__.md)
- [graph.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/graph.md)
- [logging.md](/Users/daniellim/Documents/random/rtl-comrade/docs/harness/logging.md)

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

`App` searches for this file by ascending the directory tree from the current working directory, stopping at the git repository root (a directory containing `.git/`) or the filesystem root. The file name defaults to `rtl_comrade_config.yaml` and can be overridden with `--config-file`.

The config is parsed into `RtlComradeConfig` and `CommandConfig` via `pyserde`.

## Two-Pass Argument Parsing

`App.__init__` uses `argparse` with `parse_known_args` for a lightweight preliminary pass to extract `--config-file` and `--level` before typer is initialized. This lets logging and config discovery happen before the typer app is constructed.

The same options are re-declared as typer parameters on the `main` callback so they appear correctly in `--help` output. The argparse pass is intentionally silent — it does not validate or reject unknown arguments.

## Subcommand Registration

Each entry in `config.commands` becomes a typer subcommand. Running `rtl-comrade <name>` calls `run_graph` with the configured graph path.

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

`run_graph(config_path)` builds a `Graph` with `Graph.from_file`, runs it with `asyncio.run`, then raises `typer.Exit(1)` if `self.handler.failure` is set. This converts deferred `ERROR`-level log failures into a non-zero process exit code.

## Known Gaps

- Graph paths in the config are resolved relative to the runner's working directory, not relative to the config file's location.
- Subcommands currently have no additional options; graph config is not introspected for dynamic CLI parameters.

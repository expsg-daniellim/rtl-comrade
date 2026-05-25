# rtl-comrade

`rtl-comrade` is a modular version of `rtl-buddy` based on an executable dependency graph, intended for modular construction, rapid iteration and easy extension with a high degree of code reuse. `rtl-buddy` commands become individual graphs that are executed by the harness. The rest of this README covers features specific to the harness. Detailed docs can be found in `docs/`.

## Running

```bash
uv run rtl-comrade <command> [graph-options]
```

`<command>` is a subcommand name defined in `rtl_comrade_config.yaml`. Running with no subcommand shows help.

Subcommands may accept additional options or arguments defined in the graph YAML via CLI edges (see `docs/harness_configs/graph.md`). These appear in the subcommand's `--help` output and are injected directly into the graph at runtime. If a subcommand has required CLI parameters, running it with no arguments shows help automatically.

## Options

| Option | Default | Description |
| ------ | ------- | ----------- |
| `--level <LEVEL>`      | `INFO`                    | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, or `FATAL` (case-insensitive) |
| `--config-file <NAME>` | `rtl_comrade_config.yaml` | Filename to search for when ascending the directory tree; replaces the default name           |

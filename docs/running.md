# Running rtl-comrade

## Prerequisites

- **uv** — see [installation instructions](https://docs.astral.sh/uv/#installation)
- **Python 3.11 or later** — uv will install this automatically if needed

## Setup

On setup, run once to install the locked environment:

```bash
uv sync --locked
```

Re-run whenever `pyproject.toml` or `uv.lock` changes.

## Basic invocation

```bash
uv run rtl-comrade <command> [graph-options]
```

`<command>` is a subcommand name defined in `rtl_comrade_config.yaml`. Running with no subcommand shows help.

Subcommands may accept additional options or arguments defined in the graph YAML via CLI edges (see `docs/harness_configs/graph.md`). These appear in the subcommand's `--help` output and are injected directly into the graph at runtime. If a subcommand has required CLI parameters, running it with no arguments shows help automatically.

## Options

| Option | Default | Description |
|---|---|---|
| `--level <LEVEL>` | `INFO` | Logging level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, or `FATAL` (case-insensitive) |
| `--config-file <NAME>` | `rtl_comrade_config.yaml` | Filename to search for when ascending the directory tree; replaces the default name |

Options must appear before the subcommand:

```bash
uv run rtl-comrade --level debug <command>
uv run rtl-comrade --config-file other_config.yaml <command>
uv run rtl-comrade --level debug --config-file other_config.yaml <command>
```

## Config file discovery

By default the tool searches for `rtl_comrade_config.yaml` by ascending the directory tree from the current working directory, stopping at the git root or the filesystem root.

The config file maps subcommand names to graph paths:

```yaml
commands:
  test:
    path: "graphs/test.yaml"
    help: "optional help string"
```

Graph paths are resolved relative to the config file's directory.

See `docs/harness_configs/rtl_comrade_config.md` for the full config file format, and `docs/harness_configs/graph.md` for the graph YAML format.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, or no subcommand given (help shown) |
| `1` | Graph run failed (any `ERROR`-level log during execution), usage error, or abort |

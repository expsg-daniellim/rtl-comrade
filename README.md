# rtl-comrade

`rtl-buddy` is a monolithic CLI tool for automating tests, regressions, testplan, fpga builds, rtl releases. `rtl-comrade` is a modular version of `rtl-buddy` based on an executable dependency graph, intended for modular construction, rapid iteration and easy extension with a high degree of code reuse. `rtl-buddy` commands become individual graphs that are executed by the harness. The rest of this README covers features specific to the harness. Detailed docs can be found in `docs/`.

The implementations of each command have deferred slightly from baseline `rtl_buddy` v1.4.0, see [`docs/divergences.md`](docs/divergences.md).

## Setup

Requires [uv](https://docs.astral.sh/uv/#installation) and Python 3.11 or later (uv installs it if needed). Install the locked environment once:

```bash
uv sync --locked
```

Re-run whenever `pyproject.toml` or `uv.lock` changes. See [`docs/running.md`](docs/running.md) for full setup, invocation, and config-discovery details.

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

## Commands

Commands are defined in `rtl_comrade_config.yaml`, each mapping a subcommand name to a graph. For invdividual documentation on the `rtl_buddy`-equivalent commands, see [`docs/graphs/index.md`](docs/graphs/index.md).

| Command | Graph | Description |
| ------- | ----- | ----------- |
| `test`  | `graphs/test.yaml` | Compile and simulate a SystemVerilog/UVM test suite — see [`docs/graphs/test.md`](docs/graphs/test.md) |

For example, to run the test named `basic` from a project's suite directory:

```bash
uv run rtl-comrade test basic
```

# `rtl_comrade_config.yaml`

Top-level CLI config. Maps subcommand names to graph paths.

## Discovery

The harness searches for this file by ascending the directory tree from the current working directory, stopping at the git root (a directory containing `.git/`) or the filesystem root. The filename searched for defaults to `rtl_comrade_config.yaml` and can be changed with `--config-file <NAME>`.

## Schema

```yaml
commands:
  <name>:
    path: <str>      # required — path to the graph YAML, relative to this config file's directory
    help: <str>      # optional — help string shown in --help output
```

`commands` is a required mapping. Each key becomes a CLI subcommand.

## Example

```yaml
commands:
  test:
    path: "graphs/test.yaml"
    help: "Compile and simulate a SystemVerilog/UVM test suite."
```

Running `uv run rtl-comrade test` loads `graphs/test.yaml` and executes it.

## Notes

- Subcommands currently have no additional options beyond those defined on the top-level CLI.

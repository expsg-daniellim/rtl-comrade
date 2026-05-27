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
  alu:
    path: "graphs/graph.yaml"
  add:
    path: "graphs/graph2.yaml"
    help: "Adds two numbers pairwise from a file."
```

Running `uv run rtl-comrade add` loads `graphs/graph2.yaml` and executes it.

## Notes

- Subcommands currently have no additional options beyond those defined on the top-level CLI.

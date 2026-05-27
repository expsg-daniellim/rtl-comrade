# Graph YAML

Defines the nodes, edges, and plugin sources for a single graph. Passed to `Graph.from_file(path)`.

<!-- TODO: author a dedicated authoritative example graph that covers all config features -->

`graphs/graph2.yaml` is used as a working example below.

## Top-level keys

```yaml
modules:    # list of plugin directory paths for module discovery
contracts:  # list of plugin directory paths for contract discovery
nodes:      # list of node definitions
edges:      # list of directed connections between node ports
```

`modules` and `contracts` are paths to plugin directories. Each directory is resolved relative to the graph YAML file's own directory and must contain either a `config.yaml` manifest or one or more `.py` files for auto-discovery. See `docs/harness_configs/plugin_manifest.md`.

## Node definition

```yaml
nodes:
- id: <str>                  # required — unique node identifier
  module: <str>              # required — plugin name from a modules manifest
  contract: <str>            # optional — plugin name from a contracts manifest; defaults to "default"
  config:                    # optional — passed to module __init__ as config
    key: value
  contract_config:           # optional — passed to contract __init__ as config
    key: value
```

### Path-relative config values

If a module's `Config` class contains a `Path`-typed field, its value in the graph YAML can use `{graph}` as the first path component to resolve it relative to the graph file's directory:

```yaml
config:
  file: "{graph}/data/input.txt"
```

The harness replaces `{graph}` with the graph file's parent directory at node construction time. Plain relative paths (without `{graph}`) are left unchanged and will be resolved relative to the runner's working directory when the module opens them.

## Edge definition

An edge connects a source to a destination port. The source can be either a node output port or a CLI argument.

### Node source

```yaml
edges:
- src:
    node: <str>              # source node id
    port: <str>              # optional — output port name on the source; defaults to "default"
  dst:
    node: <str>              # destination node id
    port: <str|int>          # optional — input port name or 1-based index; defaults to 1
```

### CLI source

```yaml
edges:
- src:
    cli: <str>               # required — CLI parameter name (must be a valid Python identifier)
    option: <bool>           # optional — true (default) for --<name> option; false for positional argument
    type: <str>              # optional — primitive type: int, float, bool, str; defaults to str
    default: <value>         # optional — default value; if absent the parameter is required
    help: <str>              # optional — help text shown in --help output
  dst:
    node: <str>              # destination node id
    port: <str|int>          # optional — input port name or 1-based index; defaults to 1
```

A CLI edge injects a value supplied on the command line directly into a destination node's input port. The harness creates a virtual `ModuleCLI` node for each distinct `cli` name and wires it to the declared destination. The parameter is surfaced as a subcommand option or argument depending on the `option` field. When `option: false`, the positional argument order matches the declaration order of CLI edges in the `edges` list.

The destination `port` field accepts either a string name matching a `run(...)` parameter name or a 1-based integer index into the parameter list.

## Example

```yaml
contracts:
- "contracts"
modules:
- "modules"
nodes:
- id: file-1
  module: fileread
  contract: "zip"
  config:
    file: "file1.txt"
- id: file-2
  module: fileread
  contract: "zip"
  config:
    file: "file2.txt"
- id: add
  module: add
  contract: "zip"
- id: output
  module: stdout
  contract: "zip"
edges:
- src:
    node: file-1
  dst:
    node: add
- src:
    node: file-2
  dst:
    node: add
    port: 2
- src:
    node: add
  dst:
    node: output
```


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

`modules` and `contracts` are paths to plugin directories. Each directory is resolved relative to the runner's working directory and must contain either a `config.yaml` manifest or one or more `.py` files for auto-discovery. See `docs/harness_configs/plugin_manifest.md`.

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

## Edge definition

```yaml
edges:
- src:
    node: <str>              # source node id
    port: <str>              # optional — output port name on the source; defaults to "default"
  dst:
    node: <str>              # destination node id
    port: <str|int>          # optional — input port name or 1-based index; defaults to 1
```

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


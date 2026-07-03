# Graph YAML

Defines the nodes, edges, and plugin sources for a single graph. Passed to `Graph.from_file(path)`.

<!-- TODO: author a dedicated authoritative example graph that covers all config features -->

`graphs/test.yaml` is the reference graph; a minimal illustrative example is shown below.

## Top-level keys

```yaml
modules:    # list of plugin directory paths for module discovery
contracts:  # list of plugin directory paths for contract discovery
nodes:      # list of node definitions
edges:      # list of directed connections between node ports
logging:    # optional — per-graph custom logging configuration
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
  cli_config:                # optional — CLI-supplied module config fields
    <field>: <cli-param>     # field name maps to a CLI parameter descriptor
  cli_contract_config:       # optional — CLI-supplied contract config fields
    <field>: <cli-param>     # field name maps to a CLI parameter descriptor
  contract_port_mappings:    # optional — declares the contract-port input surface (see below)
    <contract-port>: [<module-param>, ...]  # contract port name → module run(...) params it forwards to
```

`<cli-param>` has the same fields as a CLI edge source:

```yaml
cli: <str>        # required — CLI parameter name (must be a valid Python identifier)
option: <bool>    # optional — true (default) for --<name> option; false for positional argument
type: <str>       # optional — primitive type: int, float, bool, str; defaults to str
default: <value>  # optional — default value; if absent the parameter is required
help: <str>       # optional — help text shown in --help output
```

Each `<field>` under `cli_config` or `cli_contract_config` is the name of the corresponding field in the module's or contract's `Config` dataclass. The harness injects the CLI-supplied value into the config dict before calling the node constructor, so the module or contract receives it through the normal serde deserialization path.

If a field name appears in both `config` and `cli_config` (or both `contract_config` and `cli_contract_config`), the CLI value takes precedence and the harness emits a warning at startup.

A `cli` name may be reused across edges, `cli_config`, and `cli_contract_config` entries to wire one CLI parameter to several destinations — every reuse must declare an identical descriptor (same `option`, `type`, `default`, and `help`). The name is surfaced as a single subcommand parameter regardless of how many times it appears. Two occurrences of the same `cli` name with differing descriptor fields are a fatal error.

Do not use `help` as a `cli` name (or as the port name a CLI parameter feeds): the resulting `--help` collides with the auto-generated help flag. A module `run(...)` argument that names a builtin/keyword can carry a trailing underscore to avoid shadowing it in Python (`list_`); the underscore is dropped for the external port name, so `dst.port` and any `cli` targeting it use the bare name (`list`) — see [structure.md](../harness/structure.md).

### Contract port mappings

`contract_port_mappings` declares the input surface a contract presents when it differs from the module's own `run(...)` signature — typically a contract wrapping a `**kwargs` module that reads its own named "contract ports" and forwards them to module parameters internally. Each key is a contract-accepted port name (where edges deliver and what the contract reads); its value lists the module parameters that port forwards to.

```yaml
nodes:
- id: agg
  module: collect          # e.g. run(self, **kwargs)
  contract: keyed_join
  contract_port_mappings:
    left: [a]              # edges to port "left" feed module param a
    right: [b]
```

Declaring it makes the node's input surface the contract ports rather than the module signature, so edge destination validation and static deadlock screening run against the true surface. The node becomes **definite** even over a `**kwargs` module: an edge to an undeclared contract port is rejected as an invalid destination port instead of being silently accepted. A contract port is treated as default-bearing only when **every** module parameter it forwards to has a Python default; over a `**kwargs` module no parameter has a signature default, so contract ports are first-run-required unless fed by an edge. The harness performs no forwarding itself — the contract already returns module-parameter-keyed results — so this is a static-analysis declaration with no runtime effect.

When the module is definite, every listed target must name a real `run(...)` parameter; an unknown target is a fatal configuration error. Over a non-definite (`**kwargs`) module the target names are unconstrained, so that check is skipped while edge validation against the contract ports stays strict. A contract port mapping to an empty target list forwards to nothing, so it cannot inherit a default and stays first-run-required (it must be fed by an edge).

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
    required: <bool>         # optional — when true, the default contract awaits a real value on this port even if the input has a default; defaults to false
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
    required: <bool>         # optional — when true, the default contract awaits a real value on this port even if the input has a default; defaults to false
```

A CLI edge injects a value supplied on the command line directly into a destination node's input port. The harness creates one virtual `ModuleCLI` node per distinct `cli` name and wires it to every destination declared for that name, so a single CLI parameter can fan out to multiple input ports (each occurrence must declare an identical descriptor). The parameter is surfaced as a subcommand option or argument depending on the `option` field. When `option: false`, the positional argument order matches the declaration order of CLI edges in the `edges` list.

The destination `port` field accepts either a string name matching a `run(...)` parameter name or a 1-based integer index into the parameter list.

The optional `required` field overrides the default contract's treatment of a default-bearing input. Normally an input with a Python default value never blocks: if no value is queued, the contract omits it and the module's default applies. Marking the destination `required: true` forces the contract to await a real value on that port before each invocation, ignoring the input's default. This is a per-wiring property of the edge's destination, not of the module signature. (A port that has no default is always awaited regardless.)

## Logging configuration

The optional `logging` block configures per-graph custom logging. It is resolved lazily when the subcommand runs (not at startup) and applies to that run only. See `docs/harness/logging.md` for the full processor/handler model and its two hard constraints, and `docs/logger/implementation.md` for how to write a logging plugin.

```yaml
logging:
  include_default: <bool>   # optional — defaults to true
  handlers:                 # optional — ordered list of custom handler entries
  - path: <str>             # required — plugin file, resolved relative to the graph file's directory
    name: <str>             # required — exported callable/class to select from that file
    config:                 # optional — passed as __init__(config=...) when the class declares a `config` param
      key: value
```

Each entry under `handlers` references one exported object selected by `name` from the file at `path`. The harness classifies the resolved object:

- if it is a `logging.Handler` subclass, it is instantiated and appended to the root logger as a full handler;
- otherwise it must be a **structlog processor** — a callable with signature `(logger, method_name, event_dict)` — which joins the harness handler's formatter chain in list order.

`config` is only consumed when the selected object is a class whose `__init__` declares a `config` parameter; if the class also exposes a `Config` dataclass the config dict is deserialized into it (and `{graph}`-relative `Path` fields are resolved against the graph file's directory, as elsewhere in this schema). Supplying `config` for a function, a pre-built instance, or a class that takes no `config` is a mistake and the harness warns.

`include_default` (default `true`) controls the harness handler's terminal renderer:

- `true`: the harness handler's `ConsoleRenderer` stays terminal; processor entries run before it and must return an event dict.
- `false`: `ConsoleRenderer` is dropped and the **last** processor entry becomes the terminal renderer (and must return `str`); earlier processors return event dicts. With no processors the harness handler renders nothing.

Two constraints are load-bearing and documented in full in `docs/harness/logging.md`:

- a Handler-type entry is added to the root logger after the harness handler, so it **never observes `CRITICAL` records** — the harness handler raises `typer.Exit(1)` first;
- a Handler-type entry inherits only the shared preprocessors, **not** the harness handler's `ProcessorFormatter`/`ConsoleRenderer`/`include_default`/`DropEvent` handling; without its own `ProcessorFormatter` it receives the raw event `dict` as `record.msg`.

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


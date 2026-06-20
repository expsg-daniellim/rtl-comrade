# `unit`

**Class:** `UnitContract` (`contracts/unit.py`)

[Back to index](index.md)

Reads exactly one item from each required port and invokes the module once. Subsequent calls return `EndSentinel` immediately. Suitable for nodes that should run exactly once regardless of how many items are available upstream.

## Config

None.

## Termination

After the single invocation, every subsequent `get_inputs()` call returns `EndSentinel`. If any port ends before delivering a value, an error is logged and the node shuts down without invoking the module. If a port sends a second item after the first was consumed, the duplicate is logged as an error.

## Example use cases

**Loading configuration once at startup.** A node reads a config file path from one port, loads the file, and emits parsed settings. It should run exactly once no matter how many downstream consumers are connected.

```yaml
nodes:
  - id: load_config
    module: parse_config_file
    contract: unit
```

**One-shot side effects.** A node that creates a database table or initialises external state should not be triggered more than once. `unit` enforces this without the module needing to guard against repeat calls.

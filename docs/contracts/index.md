# Available Contracts

A contract is the scheduling policy for a node. It decides when the node is allowed to run and which input payloads to supply. The module sees only raw values; all stream coordination happens in the contract.

For background on the contract interface and how to write your own, see [implementation.md](implementation.md).

## Sentinels

Some contracts use domain-specific sentinel values emitted as payload values (distinct from `EndSentinel`, which signals stream termination):

| Sentinel | Imported from | Used by |
|---|---|---|
| `GroupEnd` | `contracts.sentinels` | `group_until_end` — signals the end of one group while keeping the port open |

For the expected structure of per-contract files, see [doc-structure.md](doc-structure.md).

## Contracts

| Contract | Summary |
|---|---|
| [default](default.md) | General-purpose; blocks on required inputs, supports persistent cached ports and default-valued ports |
| [zip](zip.md) | Pairs items by position across all ports; all ports must deliver at the same rate |
| [unit](unit.md) | Runs the module exactly once; errors if any port delivers more than one item |
| [keyed\_join](keyed_join.md) | Joins items from all ports by a correlation key — the `key_field` attribute or dict entry of each payload (default `"key"`) |
| [latest](latest.md) | Caches the most-recent value from state ports; triggers on each item from trigger ports |
| [group\_until\_end](group_until_end.md) | Accumulates items into a list until a `GroupEnd` sentinel; passes the full batch to the module |
| [branch\_aware\_join](branch_aware_join.md) | Like `keyed_join` but uses each port's `branch_labels` to exclude ports whose control-flow arm was not selected for a key |

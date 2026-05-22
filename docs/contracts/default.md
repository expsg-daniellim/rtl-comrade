# `default`

**Class:** `DefaultContract` (built-in, `src/rtl_comrade/`)

[Back to index](index.md)

The general-purpose workhorse. On each invocation it blocks until every required port has delivered a value, then assembles the invocation from required inputs, optional/persistent cached inputs, and synthesized defaults — in that precedence order.

## Config

```yaml
contract: default
contract_config:
  persistent_inputs: [config]   # optional; omit if no persistent ports are needed
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `persistent_inputs` | `list[str]` | `[]` | Port names whose last-received value is reused on future invocations where no new value has arrived |

## Termination

Ends when any required (non-special) port ends. If some required ports have already delivered data and others have not, the mismatch is logged as an error before the node shuts down.

## How invocation inputs are assembled

1. **Required ports** — block until a real value arrives
2. **Special ports with a queued payload** — consume it eagerly via non-blocking read
3. **Persistent ports (cached)** — use the most recently received value
4. **Default-valued ports with nothing queued** — omitted from the dict; Python's own default activates when the module is called

## Example use cases

**Enriching each item with a slowly-changing config.** A config node runs once, emits a settings object, and that object is reused for every subsequent work item processed by a downstream node.

```yaml
nodes:
  - id: enrich
    module: enrich_record
    contract: default
    contract_config:
      persistent_inputs: [settings]
```

Port `settings` is persistent: the first value received is cached and replayed on every later invocation without blocking on the settings stream again.

**Simple one-to-one stream processing.** No persistent inputs needed; omit `contract_config` entirely.

```yaml
nodes:
  - id: transform
    module: transform_record
    contract: default
```

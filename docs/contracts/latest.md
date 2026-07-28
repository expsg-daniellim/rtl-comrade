# `latest`

**Class:** `LatestContract` (`contracts/latest.py`)

[Back to index](index.md)

Maintains the most-recent value from one or more state ports and invokes the module once per item on trigger ports, pairing each trigger with the current cached state. State ports are read eagerly at first invocation and then drained non-blockingly between trigger invocations; trigger ports drive the invocation cadence.

## Config

```yaml
contract:
  name: latest
  config:
    trigger_ports: [document]
```

| Field | Type | Purpose |
|---|---|---|
| `trigger_ports` | `list[str]` | Port names that trigger an invocation; all other ports are treated as state |

Every port not listed in `trigger_ports` is a state port. At least one trigger port and at least one state port are expected for this contract to be useful.

## Termination

Ends when any trigger port ends. State port termination stops further state updates but does not itself end the node.

## Example use cases

**Applying a model to a stream of documents.** A model-loading node emits a heavy model object once on a `model` port. A separate source emits one document per item on a `document` port. The inference node uses `latest` so the model is loaded once and reused across all documents.

```yaml
nodes:
  - id: infer
    module: run_inference
    contract:
      name: latest
      config:
        trigger_ports: [document]
```

Every time a `document` arrives the module is called with the current `model` value. If a new model arrives between documents (e.g. a hot-reload signal), the next document invocation picks it up automatically.

**Enriching requests with a periodically refreshed config.** A polling node pushes updated settings on a `config` port whenever the remote config changes. An enrichment node uses `latest` to always stamp outgoing records with the most-recent settings without blocking on config delivery.

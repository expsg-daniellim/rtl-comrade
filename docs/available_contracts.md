# Available Contracts

A contract is the scheduling policy for a node. It decides when the node is allowed to run and which input payloads to supply. The module sees only raw values; all stream coordination happens in the contract.

For background on the contract interface and how to write your own, see [contract-implementation.md](contract-implementation.md).

---

## `default`

**Class:** `DefaultContract` (built-in, `src/rtl_comrade/`)

The general-purpose workhorse. On each invocation it blocks until every required port has delivered a value, then assembles the invocation from required inputs, optional/persistent cached inputs, and synthesized defaults — in that precedence order.

### Config

```yaml
contract: default
contract_config:
  persistent_inputs: [config]   # optional; omit if no persistent ports are needed
```

| Field | Type | Default | Purpose |
|---|---|---|---|
| `persistent_inputs` | `list[str]` | `[]` | Port names whose last-received value is reused on future invocations where no new value has arrived |

### Termination

Ends when any required (non-special) port ends. If some required ports have already delivered data and others have not, the mismatch is logged as an error before the node shuts down.

### How invocation inputs are assembled

1. **Required ports** — block until a real value arrives
2. **Persistent ports (cached)** — use the most recently received value
3. **Persistent ports (defaulted)** — synthesize from the module's Python default if no value has arrived yet
4. **Default-only ports** — synthesize from the module's Python default without caching

### Example use cases

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

---

## `zip`

**Class:** `ZipContract` (`contracts/contracts.py`)

Pairs items from all input ports by position: first-with-first, second-with-second, and so on. All ports must deliver items at the same rate. This is the simplest correct contract when streams are guaranteed to be aligned.

### Config

None.

### Termination

Ends when any port ends. If some ports have delivered data and others have delivered `EndSentinel` for the same invocation, the mismatch is logged as an error.

### Example use cases

**Processing aligned input/output pairs.** Two upstream nodes produce a `query` stream and an `answer` stream at exactly the same rate. The `evaluate` node receives one `(query, answer)` pair per invocation.

```yaml
nodes:
  - id: evaluate
    module: evaluate_pair
    contract: zip
```

**Zipping an index stream with a value stream.** A generator emits `(index, value)` on separate ports in lock-step; the downstream node receives both together.

---

## `unit`

**Class:** `UnitContract` (`contracts/unit_contract.py`)

Reads exactly one item from each required port and invokes the module once. Subsequent calls return `EndSentinel` immediately. Suitable for nodes that should run exactly once regardless of how many items are available upstream.

### Config

None.

### Termination

After the single invocation, every subsequent `get_inputs()` call returns `EndSentinel`. If any port ends before delivering a value, an error is logged and the node shuts down without invoking the module. If a port sends a second item after the first was consumed, the duplicate is logged as an error.

### Example use cases

**Loading configuration once at startup.** A node reads a config file path from one port, loads the file, and emits parsed settings. It should run exactly once no matter how many downstream consumers are connected.

```yaml
nodes:
  - id: load_config
    module: parse_config_file
    contract: unit
```

**One-shot side effects.** A node that creates a database table or initialises external state should not be triggered more than once. `unit` enforces this without the module needing to guard against repeat calls.

---

## `keyed_join` / `required_inputs_by_key`

**Class:** `KeyedJoinContract` (`contracts/keyed_join.py`)

Groups incoming items by a correlation key extracted from each payload dict and invokes the module when all required ports have delivered a value for the same key. Items may arrive interleaved across ports and are buffered until a complete group is available. `required_inputs_by_key` is an alias for the same class.

### Config

```yaml
contract: keyed_join
contract_config:
  key_field: test_id
```

| Field | Type | Purpose |
|---|---|---|
| `key_field` | `str` | Name of the field within each payload dict used as the correlation key |

Each payload must be a `dict` containing `key_field`. The key type must support `<` comparison (e.g. `int`, `str`) because ties between simultaneously complete keys are broken by minimum value.

### Termination

Ends when any port ends. Buffered items whose key is incomplete at that point are logged as an error.

### Example use cases

**Joining results from two independent processing pipelines.** A test harness runs each test through a linter and a type-checker in parallel. Results from both arrive keyed by `test_id` in arbitrary order. `keyed_join` assembles each test's complete report before the aggregator module runs.

```yaml
nodes:
  - id: aggregate_results
    module: build_test_report
    contract: keyed_join
    contract_config:
      key_field: test_id
```

Linter port delivers `{"test_id": 42, "lint_ok": true}`. Type-checker port delivers `{"test_id": 42, "type_ok": false}`. The module is invoked once with both, keyed on `42`.

**Enriching records from two heterogeneous sources.** A customer record arrives from one API and an order history arrives from another, both carrying `customer_id`. `keyed_join` ensures the module always sees both together.

---

## `latest`

**Class:** `LatestContract` (`contracts/latest.py`)

Maintains the most-recent value from one or more state ports and invokes the module once per item on trigger ports, pairing each trigger with the current cached state. State ports are read eagerly at first invocation and then drained non-blockingly between trigger invocations; trigger ports drive the invocation cadence.

### Config

```yaml
contract: latest
contract_config:
  trigger_ports: [document]
```

| Field | Type | Purpose |
|---|---|---|
| `trigger_ports` | `list[str]` | Port names that trigger an invocation; all other ports are treated as state |

Every port not listed in `trigger_ports` is a state port. At least one trigger port and at least one state port are expected for this contract to be useful.

### Termination

Ends when any trigger port ends. State port termination stops further state updates but does not itself end the node.

### Example use cases

**Applying a model to a stream of documents.** A model-loading node emits a heavy model object once on a `model` port. A separate source emits one document per item on a `document` port. The inference node uses `latest` so the model is loaded once and reused across all documents.

```yaml
nodes:
  - id: infer
    module: run_inference
    contract: latest
    contract_config:
      trigger_ports: [document]
```

Every time a `document` arrives the module is called with the current `model` value. If a new model arrives between documents (e.g. a hot-reload signal), the next document invocation picks it up automatically.

**Enriching requests with a periodically refreshed config.** A polling node pushes updated settings on a `config` port whenever the remote config changes. An enrichment node uses `latest` to always stamp outgoing records with the most-recent settings without blocking on config delivery.

---

## `group_until_end`

**Class:** `GroupUntilEndContract` (`contracts/group_until_end.py`)

Accumulates items from each port into a list until every port emits a `GroupEnd` sentinel payload. Each call to `get_inputs` collects exactly one group. The module receives each port's entire batch as a list. Multiple groups per stream are supported by calling `get_inputs` repeatedly; the `GroupEnd` sentinel resets the accumulator.

### Config

None.

### Sentinel

`GroupEnd` is imported from `contracts.sentinels`. Emit it as a payload value — not as an `EndSentinel` — to signal the end of one group while keeping the port open for the next.

```python
from contracts.sentinels import GroupEnd

async def run(self, items):
    ...
    yield ("out", GroupEnd())   # closes current group
```

The stream itself ends with an ordinary `EndSentinel` from the upstream node.

### Termination

Ends when any port delivers an `EndSentinel` mid-group. The accumulated items for the current incomplete group are discarded.

### Example use cases

**Aggregating all log lines for a job before writing a report.** A log-streaming node emits one line per item and a `GroupEnd` when the job finishes. The reporting node accumulates the full log batch and writes one report per job.

```yaml
nodes:
  - id: write_report
    module: write_job_report
    contract: group_until_end
```

The `run` method receives `{"lines": ["line 1", "line 2", ...]}` rather than individual lines.

**Collecting all items from a paginated source before processing.** A paginated API fetcher emits items one at a time and a `GroupEnd` at each page boundary. A downstream node processes each complete page as a batch.

**Running a batch computation once all inputs are ready.** Multiple upstream nodes each produce a sequence of partial results, signalling completion with `GroupEnd`. The downstream node accumulates all partial results and produces one final output.

---

## `branch_aware_join`

**Class:** `BranchAwareJoinContract` (`contracts/branch_aware_join.py`)

Joins inputs by correlation key like `keyed_join`, but accounts for control-flow branches that intentionally skip some ports. A port carrying `BranchSkip(key=k)` is treated as satisfied for key `k` and omitted from the dict passed to the module. This allows fan-in after `if/else` routing nodes where only one branch executes per item.

### Config

```yaml
contract: branch_aware_join
contract_config:
  key_field: request_id
```

| Field | Type | Purpose |
|---|---|---|
| `key_field` | `str` | Field within each real-data payload dict used as the correlation key |

### Sentinel

`BranchSkip` is imported from `contracts.sentinels`. Emit it as a payload value on a port that was bypassed for a given key.

```python
from contracts.sentinels import BranchSkip

async def run(self, items, key):
    if condition:
        yield ("branch_a", result)
        yield ("branch_b", BranchSkip(key=key))
    else:
        yield ("branch_a", BranchSkip(key=key))
        yield ("branch_b", result)
```

The `key` argument to `BranchSkip` must match the value that would be found at `payload[key_field]` on real data items so the contract can correlate them.

### Termination

Ends when any port ends.

### Module side: defaulted parameters

Because skipped ports are absent from the dict passed to the module, any port that may be skipped must have a default value in the module's `run(...)` signature. The harness will not inject a value for an absent port.

```python
def run(self, branch_a=None, branch_b=None, **kwargs):
    result = branch_a or branch_b
    ...
```

### Example use cases

**Fan-in after if/else routing.** A router node inspects each record's `type` field and sends it down one of two processing branches. Both branches feed a final aggregator. The router emits `BranchSkip` on whichever branch was not taken so the aggregator knows both branches are accounted for and can fire.

```yaml
nodes:
  - id: aggregator
    module: merge_results
    contract: branch_aware_join
    contract_config:
      key_field: request_id
```

For `request_id=7`, branch A delivers `{"request_id": 7, "result": "ok"}` while branch B delivers `BranchSkip(key=7)`. The module receives `{"branch_a": <payload>}` — branch B is absent, so the module's `branch_b=None` default applies.

**Optional enrichment step.** An enrichment node runs only for records that meet a relevance threshold. A bypass path emits `BranchSkip` for records that do not. The downstream joiner uses `branch_aware_join` so both paths converge without requiring the enrichment node to emit dummy outputs.

# Spec 09: flag-gate (`FlagGateMod`)

**Depends on:** nothing — the module is payload-agnostic and domain-agnostic.
**References:** [`docs/harness_configs/graph.md`](../docs/harness_configs/graph.md) (multi-source input ports, `required`), [`docs/harness/branch_labels.md`](../docs/harness/branch_labels.md) (how the arms are derived and propagated), [`docs/contracts/branch_aware_join.md`](../docs/contracts/branch_aware_join.md) (the distinct-port rejoin), `modules/rtl_buddy/control.py` (`EarlyStopGateMod`, the existing gate), [`docs/modules/route-list-mode.md`](../docs/modules/route-list-mode.md) (the existing boolean router); consumers: the optional transforms of specs [04](04-filelist-flatten.md), [05](05-filelist-strip.md), [06](06-filelist-dedup.md).

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, output forms) and `docs/harness/branch_labels.md` (a module whose outputs sit under `if`/`else` is a **branch origin**; its arms are what let a downstream join drop the path not taken).

## Goal

Route one value to one of two output ports according to a boolean input. Nothing else: no transform of the value, no config, no knowledge of what the value is.

The pipeline needs it because [00-overview](00-overview.md#why-this-pipeline-exists) makes a capability difference *which nodes are wired*, and a graph's node set is fixed at load time — `docs/harness_configs/graph.md` has no conditional wiring. So a single graph honouring a runtime flag (`--flatten`, `--strip`, `--deduplicate`) needs the choice expressed as a branch **inside** the graph, and this is the smallest node that expresses it.

## Surface

```
contract:          default   (persistent_inputs: [flag], with required: true on the flag edge — see below)
inputs:            value:Any, flag:bool = False
outputs:           on  → value   (flag true)
                   off → value   (flag false)
```

```python
class FlagGateMod:
    def run(self, value:Any, flag:bool = False):
        if flag:
            yield ("on", value)
        else:
            yield ("off", value)
```

Exactly one port fires per input, and the value is re-emitted **as it arrived** — same object, not a copy or a rewrap. A `KeyedValue` therefore leaves the gate still keyed, so downstream keyed joins match on it and the gate itself never needs `unwrap`.

## Algorithm

1. `flag` true → `yield ("on", value)`; else → `yield ("off", value)`.

That is the whole module. Both ports are statically named under an `if`/`else`, so `ModuleStructure` derives the two arms straight from the AST and proves them mutually exclusive — **no `output_groups` declaration** needed. `EarlyStopGateMod` emits through `**edges`, which the AST cannot name, so it falls back to one shared arm (all-or-nothing), which is correct for a gate that re-emits every edge or none. The difference is that `FlagGateMod`'s static `if`/`else` lets the harness prove exclusivity per arm, which is what makes the downstream same-port rejoin validate.

## Rejoining the arms

A gate is only half of a bypass: the taken and untaken paths have to converge again. Which mechanism does that depends on where the two arms land.

**Same port — an alternation.** When both arms carry the same payload to the same downstream input, wire them both into that one port. An input port takes several edges when the harness can prove at most one of them ever carries data, which two arms of one `if`/`else` origin satisfy by construction (`docs/harness_configs/graph.md`, [branch_labels](../docs/harness/branch_labels.md)); the port delivers whichever arm ran and ends only once *every* source has sent its `EndSentinel`, so the arm that finishes first cannot truncate it. This is the filelist pipeline's case, and it needs no join node, no join contract and no defaulted port — the downstream node is written as though the gate were not there.

**Distinct ports — a join.** When the arms land on different ports of one module, that module uses [`branch_aware_join`](../docs/contracts/branch_aware_join.md): the gate is the branch origin, its two arms are co-arm siblings, and the arm not selected for a key is excluded from that key's assembly instead of being awaited forever, with no placeholder value emitted by anyone. Every port that can be excluded **must have a Python default** in the joining module's `run(...)` — the harness injects nothing for an absent port.

Either way, rejoin each gate's arms **before** the next gate. Labels union along a path, so a gate whose arms are still open when the next gate's arms open multiplies the paths downstream has to reason about. A rejoin is what discharges them: an input port is labelled by the **intersection** of its incoming edges' labels, so two arms of one origin cancel and leave only the inherited prefix. Chained gates therefore stay flat — each starts from the label set the previous one started from — which is what makes the three-gate chain below no harder to reason about than one gate.

That cancellation depends on the transform sitting on the `on` arm keeping a **non-defaulted** input port. A default makes the port non-gating, the arm label stops propagating through it, and the two edges into the rejoin no longer look mutually exclusive. That is reported at startup as `overloaded_srcs` rather than mis-run silently.

## Wiring — the `filelist` graph

Three flags, so three gate instances, each rejoining at the next gate's `value` port and the last at the writer's `entries`:

```yaml
nodes:
- id: gate-flatten
  module: flag-gate
  contract:
    name: default
    config:
      persistent_inputs: [ flag ]
- id: gate-strip
  module: flag-gate
  contract:
    name: default
    config:
      persistent_inputs: [ flag ]
- id: gate-dedup
  module: flag-gate
  contract:
    name: default
    config:
      persistent_inputs: [ flag ]

edges:
- src: { cli: flatten,     type: bool, default: false }
  dst: { node: gate-flatten, port: flag, required: true }
- src: { cli: strip_options, type: bool, default: false }
  dst: { node: gate-strip,   port: flag, required: true }
- src: { cli: deduplicate, type: bool, default: false }
  dst: { node: gate-dedup,   port: flag, required: true }

- src: { node: normalise,    port: entries }
  dst: { node: gate-flatten, port: value }
- src: { node: gate-flatten, port: on }
  dst: { node: flatten,      port: entries }
- src: { node: flatten,      port: entries }
  dst: { node: gate-strip,   port: value }
- src: { node: gate-flatten, port: off }
  dst: { node: gate-strip,   port: value }
- src: { node: gate-strip,   port: on }
  dst: { node: strip,        port: entries }
- src: { node: strip,        port: entries }
  dst: { node: gate-dedup,   port: value }
- src: { node: gate-strip,   port: off }
  dst: { node: gate-dedup,   port: value }
- src: { node: gate-dedup,   port: on }
  dst: { node: dedup,        port: entries }
- src: { node: dedup,        port: entries }
  dst: { node: write,        port: entries }
- src: { node: gate-dedup,   port: off }
  dst: { node: write,        port: entries }
```

The three CLI defaults are `rtl_buddy`'s own (`rtl_buddy.py:445-447` — all three `False`). `test`/`randtest`/`regression` wire none of this: no gate, `normalise → dedup → write`, matching `VlogSim`'s hard-coded `flatten=False, strip=False, deduplicate=True` (`vlog_sim.py:93`).

Both arms of a rejoin must carry the **identical** payload shape, since they feed one port — entries travel as `list[FilelistEntry]` ([spec 01](01-filelist-entry.md)) throughout the pipeline, so the bypassed arm and the transform arm carry the same shape.

## The flag needs `required: true` *and* `persistent_inputs`

Neither alone is correct, and getting it wrong misroutes silently.

`DefaultContract` treats a port as *special* — read non-blockingly, never awaited — when `(persistent and last_value is not None) or (has_default and not required)` (`src/rtl_comrade/contract_default.py:33`). `flag:bool = False` with `required` unset satisfies the second clause on every run, so the gate is never made to wait for the flag: the first value races the CLI injection and takes the `off` arm on a lost race, producing a wrong filelist with no error anywhere. `required: true` on the edge destination clears that clause and forces the first run to await a real value.

`required: true` alone then blocks forever, because the virtual CLI node injects once and ends. `persistent_inputs: [flag]` is what releases it: after the first run `last_value` is set, the first clause makes the port special again, and every later invocation replays the cached flag. The pair gives exactly "await once, replay thereafter", which is what a startup singleton against a streaming `value` needs.

## Deliverables

- `FlagGateMod` in `modules/rtl_buddy/control.py`, alongside `EarlyStopGateMod` — the graph-control file. Nothing in the module is `rtl_buddy`-specific; it sits there because that is where graph-control nodes live.
- **Manifest** — `{ name: flag-gate, class_name: FlagGateMod }` in the `- file: rtl_buddy/control.py` block of `modules/config.yaml`.
- No `Config` class, no contract.

## Tests

In `modules/tests/test_control.py`:

- `flag=True` → one result, `("on", value)`; nothing on `off`.
- `flag=False` → one result, `("off", value)`.
- `flag` omitted → the `False` default applies → `("off", value)`.
- The emitted payload **is** the input object (`result[0][1] is value`), including a `KeyedValue`, whose `key` is therefore unchanged.

## Acceptance criteria

- Tests pass.
- Exactly one of `on` / `off` fires per input, chosen by `flag`.
- The value crosses the gate unmodified and unwrapped.
- `flag-gate` → `FlagGateMod` resolves in the manifest.
- Both arms wired into one downstream input port load without `overloaded_srcs`, deliver whichever arm ran, and keep the port open until both arms have ended.
- Where the arms instead land on distinct ports, a downstream `branch_aware_join` fires for a key the gate sent down one arm, without the other arm delivering anything for that key.

## Constraints

- **Route only.** No transform, no inspection of `value`, no logging of it, no config — a gate that reads its payload is a different node.
- **Two statically-named ports** under a plain `if`/`else`. Do not emit through `**edges`, and do not add a third "both" path: two arms is what makes the branch analysis and the join exclusion work.
- **`flag` keeps its `False` default**, so a graph that never wires it gets the off arm rather than a block. A graph that *does* wire it marks the edge destination `required: true` and lists `flag` in `persistent_inputs` — both, always — rather than dropping the default; see the section above for why either alone is wrong.
- **Payload-agnostic.** `value:Any`; the gate must work identically for a bare value and a `KeyedValue`, which is why it never unwraps.

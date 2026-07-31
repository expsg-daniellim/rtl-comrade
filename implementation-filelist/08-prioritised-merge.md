# Spec 08: prioritised-merge (`PrioritisedMergeMod`)

**Depends on:** [spec 02](02-filelist-extract.md) (the per-source `entries` inputs).
**References:** [spec 03 — filelist-normalise](03-filelist-normalise.md) (consumes this node's output), `contracts/keyed_join.py`, [`docs/contracts/keyed_join.md` — Unwrapping and rewrapping](../docs/contracts/keyed_join.md#unwrapping-and-rewrapping), [00-overview — Why this pipeline exists](00-overview.md#why-this-pipeline-exists).

## Before you start

Read `docs/module-implementation/implementation.md` (port inference from `run`, `**edges` capture as in `EarlyStopGateMod`, output forms) and `contracts/keyed_join.py` (the contract this node pairs with, including its `unwrap`/`ignore` config). This is a plain module — **no new contract**.

## Why a module on `keyed_join`, not a new contract

The `test` filelist has two sources — model and testbench — and the `.f` is their ordered concatenation (model first). `keyed_join` plus a thin ranking module expresses this; no bespoke contract is needed:

- **`keyed_join` already does the hard part.** `model_entries` and `tb_entries` are each **one `list[entry]` per test key** (spec [02](02-filelist-extract.md) — `extract` materialises a list per test, not a stream). One item per port per key is exactly `keyed_join`'s shape: it groups the two lists for a `test.key`, which is also what keeps different tests' entries from colliding. The scheduling/keying is the contract's; nothing new is needed there.
- **The ordering is a parameterised concatenation, not scheduling.** Once `keyed_join` has delivered the two grouped lists, "order by priority" is just concatenating them in a configured order — a deterministic data transform. That is fine in a module; it is not the "scheduling logic in a module" CLAUDE.md forbids (the *when* is `keyed_join`'s; only the *concat order* is here, and it is pure config).
- **The contract already carries the key.** Both inputs ride the wire as `KeyedValue[list[entry]]` sharing `test.key`. With `unwrap: true` the contract hands the module the bare lists and rewraps the merged list under the assembled key, so the key never enters module code and the module never names `KeyedValue`.
- **Lists, not a stream.** Since `extract` already produces a list per test, the merge is `model_list + tb_list`; there is nothing to stream, and `dedup`/`write` downstream need the full materialised set anyway.

So `prioritised-merge` slots into the pipeline as a node between the `extract` instances and `normalise`:

```
extract-model → \
                 prioritised-merge (keyed_join) → normalise → [flatten] → [strip] → [dedup] → write
extract-tb   → /
```

## Goal

Join the per-source `entries` lists by `test.key` and emit their **priority-ordered concatenation** as one `entries` list, which the contract reattaches that same key to. Source order (model before testbench) is per-graph config, not baked into the module.

## Surface

```
contract:          keyed_join   (groups the entry ports by test key)
module config:     priorities: dict[str, int]   (input-port name → priority; lower first)
inputs:            **entries    (each a bare list[entry], unwrapped from a KeyedValue[list[entry]] keyed port; e.g. model_entries, tb_entries)
outputs:           entries → list[entry]   (priority-ordered concatenation; the contract rewraps it as KeyedValue under the assembled key)
```

```yaml
module:
  name: prioritised-merge
  config:
    priorities: { model_entries: 0, tb_entries: 1 }
contract:
  name: keyed_join
  config:
    key_field: key
    unwrap: true
```

```python
class PrioritisedMergeMod:
    @serde
    class Config:
        priorities:dict[str, int]

    def __init__(self, config):
        self.priorities = config.priorities

    def run(self, **entries):
        missing = [ name for name in entries if name not in self.priorities ]
        if len(missing) > 0:
            log.fatal("unranked_merge_port", ports=missing)
        ordered = sorted(entries, key=lambda name: (self.priorities[name], name))
        return ("entries", [ item for name in ordered for item in entries[name] ])
```

`run(self, **entries)` captures every wired keyed port (the `EarlyStopGateMod` `**edges` idiom), so the same module serves the `test` graph (two ports) and the `filelist` command (one). `keyed_join` delivers them matched by `test.key`, unwrapped to bare lists. No `ignore` list: `entries` is the only output port and it is exactly the one that must be rekeyed.

## Algorithm

1. **Validate ranking.** Every wired entry port must have a priority in `config.priorities` — else `log.fatal("unranked_merge_port", ports=…)` (an unranked source has undefined order; no silent default).
2. **Order** the delivered ports by `(priorities[name], name)` — priority ascending, name as deterministic tiebreak.
3. **Concatenate** the delivered lists in that order.
4. **Emit** `("entries", merged)`. The contract rewraps it as `KeyedValue(test.key, merged)` on the way out.

## Deliverables

- `PrioritisedMergeMod` in `modules/rtl_buddy/build.py` — `keyed_join` (`key_field: key`, `unwrap: true`) over the wired entry ports; `config.priorities` ranks them; returns `("entries", ordered-concat)`.
- **Manifest** — entry `{ name: prioritised-merge, class_name: PrioritisedMergeMod }`, registered with the full pipeline in [spec 02 Deliverables](02-filelist-extract.md#deliverables).

## Tests

In `modules/tests/test_prep.py`, driven by the module-scenario harness (`docs/modules/testing.md`):

The module is driven with bare lists, as the contract delivers them:

- Two ports `model_entries=[a,b]`/`tb_entries=[c]` with `priorities={model_entries:0, tb_entries:1}` → `("entries", [a,b,c])`. Reversed priorities → `[c,a,b]` (order follows config, not kwarg/arrival order).
- Single port `model_entries=[a,b]`, `priorities={model_entries:0}` → `("entries", [a,b])` (filelist-command case).
- A wired port absent from `priorities` → `log.fatal("unranked_merge_port", …)`.
- Two ports with equal priority → deterministic name-tiebreak order.

(Per-key grouping, interleaving across keys, and the unwrap/rewrap of the `KeyedValue` envelope are `keyed_join`'s behaviour, covered by its own tests — not re-tested here.)

## Acceptance criteria

- Tests pass.
- Output is the priority-ordered concatenation of the grouped per-source lists; the contract keys it by the shared `test.key`.
- The single-wired-port case yields a correct one-element merge with no special-casing.
- `prioritised-merge` → `PrioritisedMergeMod` resolves in the manifest.

## Constraints

- **Uses the existing `keyed_join` contract — no new contract.** The grouping/keying is the contract's; this module only concatenates and ranks.
- **Order comes from `config.priorities`, never from kwarg iteration or arrival order** — deterministic `(priority, name)`; every port ranked.
- **The module never touches the key** — no `KeyedValue` construction, no `.value`/`.key` access. `unwrap: true` goes on the `contract` plugin's `config`, the single slot it works from; an `input_contract`/`output_contract` pair would be two instances sharing no assembled key.
- `**entries` captures all wired keyed ports so one module serves both the two-source `test` graph and the one-source `filelist` command.

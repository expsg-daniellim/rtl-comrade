# Spec 12: constant (`ConstantMod`)

**Depends on:** nothing — the module is payload-agnostic and domain-agnostic.
**References:** `modules/funcs.py` (the generic-module file it joins), [`docs/module-implementation/implementation.md`](../docs/module-implementation/implementation.md) (config-bearing modules, output forms), [`docs/harness_configs/graph.md`](../docs/harness_configs/graph.md) (`required` on an edge destination), [`docs/contracts/default.md`](../docs/contracts/default.md) (`persistent_inputs`, and the special-port rule this node's consumers must account for); consumer: [filelist-extract](02-filelist-extract.md)'s `unroll` in the `test`/`randtest`/`regression` graphs ([spec 14](14-test-update.md)).

## Before you start

Read `docs/module-implementation/implementation.md` (config-bearing modules, input-port inference, output forms) and `modules/funcs.py`. This is a generic module in the same sense as `add`, `dirname` and `logger` — it names no domain type.

## Goal

Emit one configured value, once, on the `default` port. Nothing else: no inputs, no transform, no logging.

A graph needs it wherever a node's input port must carry a value that is fixed when the graph is written rather than when the run starts. `filelist-extract`'s `unroll` is that case: the `filelist` command takes it per invocation from the CLI, while `test`/`randtest`/`regression` need a fixed `true` (`vlog_sim.py:93`).

## Why a node and not a config field

The harness already models "a value fixed before the run" as a source node: a CLI edge builds a virtual `ModuleCLI` node whose `run()` emits the injected value once and ends (`src/rtl_comrade/module_cli.py`). A constant known at graph-writing time is that same thing, one step earlier, and it reaches the port the same way — through an edge, matched against the destination's `required`/`persistent` treatment like any other payload.

The alternative — folding the value into the module's `Config` — would make a port value into constructor state. The module would then need a `Config` class it has no other use for, plus two ways of learning `unroll`, and the next module with a load-time-constant port would repeat both. The node keeps `filelist-extract`'s surface untouched and puts the difference where the plan puts every other per-command difference: in the wiring. In the `test` graph `unroll` is fed by a `constant`; in the `filelist` command by a `cli` edge; the module cannot tell.

The value is also visible where a reader looks for it. A `constant` node renders on the dataflow diagram carrying what it emits — unlike a CLI bubble, whose value belongs to the invoking user and is deliberately left off the label.

## Surface

```
contract:          default   (zero-input → runs exactly once)
config:            type:str, value:Any, args:list, kwargs:dict
inputs:            none
outputs:           default → the configured value
```

```yaml
# Bare primitive — no construction
- id: unroll
  module:
    name: constant
    config: { value: true }
  contract: default

# Constructed non-primitive — single positional arg
- id: my-path
  module:
    name: constant
    config: { type: "pathlib:Path", value: "/some/path" }
  contract: default

# Constructed non-primitive — explicit args / kwargs
- id: my-obj
  module:
    name: constant
    config:
      type: "some.module:SomeClass"
      args: [1, "hello"]
      kwargs: { flag: true }
  contract: default
```

```python
class ConstantMod:
    @serde
    class Config:
        type:str = ""
        value:Any = field(default=MISSING)
        args:list = field(default_factory=list)
        kwargs:dict = field(default_factory=dict)

    def __init__(self, config):
        if config.type:
            mod_path, cls_name = config.type.rsplit(":", 1)
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            if len(config.args) > 0 or len(config.kwargs) > 0:
                self.value = cls(*config.args, **config.kwargs)
            else:
                self.value = cls(config.value)
        else:
            self.value = config.value

    def run(self):
        return ("default", self.value)
```

## Config

| field | type | default | meaning |
|---|---|---|---|
| `type` | `str` | `""` | a `module.path:ClassName` reference resolved via `importlib.import_module` + `getattr`; when empty, `value` is emitted as-is |
| `value` | `Any` | (none) | the payload to emit, or the single positional constructor argument when `type` is set and `args`/`kwargs` are absent |
| `args` | `list` | `[]` | positional arguments forwarded to the `type` constructor; when non-empty, `value` is ignored |
| `kwargs` | `dict` | `{}` | keyword arguments forwarded to the `type` constructor |

**Precedence when `type` is set:** `args`/`kwargs` present → `cls(*args, **kwargs)`. Neither present → `cls(value)`.

`value` is required when `type` is absent — a constant with nothing to emit is a configuration error, and serde reports the missing field at construction. When `type` is set with `args`/`kwargs`, `value` is unused and may be omitted.

## Contract — `default`, and why it runs once

`default`, not `unit`, for the reason [04f](../implementation-test/specs/04f-work-dir.md) gives for `work-dir`: with no ports the two contracts behave identically, and `unit` would assert a one-shot guarantee it does not supply. The one-shot behaviour comes from the node loop instead — `DefaultContract.get_inputs()` over an empty port set returns `{}`, and `Node.run()` breaks after the invocation on `len(inputs) == 0` (`src/rtl_comrade/node.py:372`). `work-dir`, `prepend-path` and `git-status` are all wired this way in `graphs/test.yaml`.

## What the consumer must declare

The node emits once and ends, so a consumer invoked more than once — every keyed node in the `test` graph — must name the port in `persistent_inputs` on its contract, exactly as it already does for `work_dir`, `builder_cfg`, `logs_dir` and `root_cfg`.

If the destination port also carries a **Python default**, the edge must additionally be marked `required: true`. Both `DefaultContract` and `KeyedJoinContract` treat a defaulted, non-required port as one that never blocks (`is_special`, `contract_default.py:33`; `can_default`, `contracts/keyed_join.py:15`), so the first invocation can fire before the constant is delivered and the module's own default silently wins. `filelist-extract`'s `unroll:bool = False` is exactly that shape, so [spec 14](14-test-update.md) marks both of its edges `required: true`. This is the standard rule for any defaulted port fed by an edge (`docs/harness_configs/graph.md`) — the same pair [spec 09](09-flag-gate.md#the-flag-needs-required-true-and-persistent_inputs) documents for `flag-gate`'s CLI-fed `flag` — and is not specific to this node.

## Algorithm

**Construction (`__init__`):**

1. If `config.type` is non-empty, split on `:` → `(mod_path, cls_name)`. `importlib.import_module(mod_path)`, then `getattr(mod, cls_name)` → `cls`.
2. If `config.args` or `config.kwargs` are non-empty, `self.value = cls(*config.args, **config.kwargs)`.
3. Otherwise `self.value = cls(config.value)`.
4. If `config.type` is empty, `self.value = config.value`.

**Run:**

1. Return `("default", self.value)`.

## Deliverables

- `ConstantMod` in `modules/funcs.py`, alongside `AddMod`, `ALUMod`, `DirnameMod` ([spec 10](10-dirname.md)) and `LoggerMod` ([spec 11](11-logger.md)).
- **Manifest** — a `{ name: constant, class_name: ConstantMod }` entry in the `- file: funcs.py` block of `modules/config.yaml`.
- No contract.

## Tests

In `modules/tests/test_funcs.py`:

**Bare value (no `type`):**
- `config.value = True` → one result, `("default", True)`.
- A `str`, an `int` and a `list` value → each emitted unchanged on `default`, showing the node is payload-agnostic.
- The emitted payload **is** the configured object (`result[0][1] is config.value` for a non-scalar), so nothing is copied or rewrapped.
- Two `run()` calls → the same value both times (the node holds no state; the once-only property belongs to the node loop, not the module, and is not re-tested here).
- `config` missing both `value` and `type` → the serde error surfaces at construction.

**Constructed value (`type` set):**
- `type: "pathlib:Path"`, `value: "/tmp"` → `("default", Path("/tmp"))`, the emitted value is a `Path` instance.
- `type: "pathlib:Path"`, `args: ["/tmp", "sub"]` → `("default", Path("/tmp", "sub"))`, positional args forwarded.
- `type: "collections:OrderedDict"`, `kwargs: { a: 1, b: 2 }` → the emitted value is an `OrderedDict` with the given entries.
- `type: "pathlib:Path"`, `args: ["/tmp"]`, `value: "ignored"` → `args` takes precedence; the emitted value is `Path("/tmp")`.
- `type` set to an unimportable module → raises at construction.
- `type` set to a valid module but absent class name → raises at construction.

## Acceptance criteria

- Tests pass.
- One emission on `default` carrying the configured value unchanged (bare) or the constructed object (`type` set).
- When `type` is set, the emitted value is an instance of the referenced class, constructed from `args`/`kwargs` or from `value` as a single positional arg.
- Wired into a keyed consumer with `persistent_inputs` (and `required: true` where the destination port has a Python default), the value reaches every invocation.
- `constant` → `ConstantMod` resolves in the manifest.

## Constraints

- **Emit only.** No inputs, no transform, no logging — a node that derived its value from something would be a different node ([dirname](10-dirname.md) is that node).
- **Payload-agnostic.** The module never inspects what it holds — bare or constructed.
- **Zero-input `default` node**, emitting on the string-literal `default` port. Do not use `unit`.
- **Domain-agnostic.** Lives in `modules/funcs.py`, names no `rtl_buddy` type, and is not part of the seven pipeline nodes ([spec 02 Deliverables](02-filelist-extract.md#deliverables)).
- **`type` resolution uses `importlib.import_module` + `getattr`.** The left side of `:` is a dotted Python import path; the right side is the class name. Do not use `eval`, `exec`, or `importlib.util`.

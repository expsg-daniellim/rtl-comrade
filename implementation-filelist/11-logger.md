# Spec 11: logger (`LoggerMod`)

**Depends on:** nothing — the module is payload-agnostic and domain-agnostic.
**References:** `modules/funcs.py` (the generic-module file it joins), [`docs/module-implementation/implementation.md`](../docs/module-implementation/implementation.md) (config-bearing modules, output rules), [`docs/harness/logging.md`](../docs/harness/logging.md) (the level→failure model this node participates in), [`docs/contracts/keyed_join.md`](../docs/contracts/keyed_join.md) (the attribute-then-dict-entry lookup rule this mirrors), [`docs/logger/implementation.md`](../docs/logger/implementation.md) (logging **plugins** — a different thing; see below).

## Before you start

Read `docs/module-implementation/implementation.md` (input-port inference, config-bearing modules, `None` emits nothing) and `docs/harness/logging.md` (`ERROR` is deferred failure, `CRITICAL` is immediate). This is a generic module in the same sense as `add` and `dirname` — it names no domain type.

**Not a logging plugin.** `docs/logger/` documents processors and handlers, which sit in the harness's own log pipeline and see every event. This is an ordinary graph node that emits one event per item it receives. The name collision is in the word only.

## Goal

Log one structured event per value that reaches it, projecting the event's fields off the value by config. Nothing else: no transform, no output ports, no knowledge of what the value is.

A graph needs it wherever a value is worth reporting but nothing consumes it — an output that would otherwise be a dead end. In this pipeline `write-filelist`'s `filelist` port is exactly that in the `filelist` command ([00-overview](00-overview.md#the-pipeline-at-a-glance) draws it into a `disconnected` sink), so a `logger` node is one candidate consumer.

## Surface

```
contract:          default
config:            level:str, event:str, mapping:dict[str, str]|str, constants:dict[str, Any]
inputs:            value:Any
outputs:           none — the module always returns None
```

The node is a terminal sink. `run(...)` never returns or yields a value, so `ModuleStructure` infers an empty emit set and the node has no output ports to wire.

```yaml
module:
  name: logger
  config:
    level: info
    event: filelist_written
    mapping: path
    constants: { context: filelist.write }
contract: default
```

## Config

| field | type | meaning |
|---|---|---|
| `level` | `str` | the log method to call — one of `debug`, `info`, `warning`, `error`, `critical`, `fatal` |
| `event` | `str` | the structured event name, the first positional argument to the log call |
| `mapping` | `dict[str, str] \| str` | how the event's kwargs are projected off `value` |
| `constants` | `dict[str, Any]` | kwargs with a fixed value, independent of `value`; also the fallback for a `mapping` key of the same name |

**`mapping` as a dict** maps kwarg name → field path on `value`, dot-delimited for nesting: `{ path: "filelist.path", key: "key" }` logs `path=value.filelist.path, key=value.key`.

**`mapping` as a str** names a single kwarg carrying the whole value: `mapping: path` logs `path=value`. It is the `{ <str>: "" }` case of the dict form, where the empty path means the root — so both forms normalise to one dict at construction and `run(...)` has a single code path.

**`constants`** does two jobs off one field, distinguished only by whether its key also appears in `mapping`:

- **A fixed field.** A key `mapping` does not name is a static kwarg on every event — `{ context: filelist.write }` stamps `context` on each one without touching `value`.
- **A default for a mapping.** A key `mapping` *does* name is the value used when that path fails to resolve. The constant is the author's declared answer for the absent case, so the failure is no longer an error: `logger_unresolved_field` is **not** logged and the constant stands. A mapping key with no constant behind it keeps the ERROR.

Constants seed the kwargs and a resolved mapping field overwrites its same-named constant, which is what makes one field serve both roles.

## Algorithm

1. **Validate at construction.** `level` not in the allowed set → `log.fatal("logger_invalid_level", level=…, allowed=…)`. A key named `event`, `exc_info`, or `stack_info` in either `mapping` or `constants` → `log.fatal("logger_reserved_kwarg", name=…)`: `event` collides with the positional event name; `exc_info` and `stack_info` are structlog-meaningful and would be interpreted rather than rendered as fields. All three are config errors that recur on every item, so they abort the run rather than deferring.
2. **Bind the level** once: `self.emit = getattr(log, config.level)`, after validation.
3. **Normalise `mapping`** to a dict: a `str` becomes `{ <str>: "" }`.
4. **Per invocation**, seed the kwargs from `constants`, walk each field path off `value` over the top, then make one log call.

```python
LOG_LEVELS = {"debug", "info", "warning", "error", "critical", "fatal"}


class LoggerMod:
    @serde
    class Config:
        level:str = "info"
        event:str = "logged_value"
        mapping:dict[str, str]|str = "value"
        constants:dict[str, Any] = field(default_factory=dict)

    def __init__(self, config):
        if config.level not in LOG_LEVELS:
            log.fatal("logger_invalid_level", level=config.level, allowed=sorted(LOG_LEVELS))
        self.event = config.event
        self.constants = config.constants
        self.mapping = {config.mapping: ""} if isinstance(config.mapping, str) else config.mapping
        reserved = {"event", "exc_info", "stack_info"}
        for name in reserved:
            if name in self.mapping or name in self.constants:
                log.fatal("logger_reserved_kwarg", name=name)
        self.emit = getattr(log, config.level)

    def run(self, value:Any):
        kwargs = dict(self.constants)
        for name, path in self.mapping.items():
            field = value
            try:
                for part in path.split(".") if path else []:   # walk the dotted path, attribute before dict entry
                    field = getattr(field, part) if hasattr(field, part) else field[part]
            except (KeyError, TypeError) as e:
                if name not in self.constants:   # a constant of the same name is the declared fallback
                    log.error("logger_unresolved_field", event=self.event, field=name, path=path, err=str(e))
                continue
            kwargs[name] = field
        self.emit(self.event, **kwargs)
```

## Field resolution

Each path segment is read as an **attribute first, then a dict entry** — the rule `keyed_join` already uses for `key_field` (`docs/contracts/keyed_join.md`), so one config shape reaches both dataclass payloads and plain dicts without the graph author knowing which arrived.

An unresolvable segment is a per-item failure, not a fatal one, and what happens depends on whether `constants` covers that kwarg:

- **No constant of that name** — `log.error("logger_unresolved_field", …)` names the kwarg and the path, that kwarg is omitted, and the remaining kwargs still log. The path may be wrong for one payload and right for the next, so the run completes and exits non-zero rather than aborting on the first.
- **A constant of that name** — the constant stays in the kwargs and nothing is logged. Declaring a fallback is declaring the absence to be expected; an ERROR there would make the fallback unusable in exactly the case it exists for.

`hasattr` guards the attribute read, so the enumerable failures are `KeyError` (missing dict entry) and `TypeError` (segment applied to something not subscriptable); both are caught.

An empty path resolves to `value` itself — that is the whole of what the `str` form does.

## Level and failure semantics

Choosing `level` chooses the node's effect on the run, per `docs/harness/logging.md`:

- `debug`/`info`/`warning` — observability only.
- `error` — sets `handler.failure`, so the run completes and **exits non-zero**. A `logger` node at this level is a deliberate failure site, not a report.
- `critical`/`fatal` — `typer.Exit(1)` on the first value that reaches the node, aborting mid-run.

That makes `level` a graph-semantics field, not a formatting one. A node added to report progress belongs at `info`.

## Deliverables

- `LoggerMod` in `modules/funcs.py`, alongside `AddMod` and `ALUMod`.
- `LOG_LEVELS` module-level constant in the same file.
- **Manifest** — a `{ name: logger, class_name: LoggerMod }` entry in the `- file: funcs.py` block of `modules/config.yaml`.
- No contract.

## Tests

In `modules/tests/test_funcs.py`:

- Dict mapping over a nested payload → one event with each kwarg resolved (`{ path: "filelist.path" }` reads `value.filelist.path`).
- Dict mapping over a plain `dict` payload → same paths resolve through dict entries, showing the attribute-then-entry rule.
- Str mapping → the whole value under that one kwarg, with no traversal.
- A path whose leaf is missing, **no constant of that name** → `log.error("logger_unresolved_field", …)`, `logging_handler.failure is True`, that kwarg absent, and the **other** kwargs still present in the emitted event.
- A path segment applied to a non-subscriptable value → same handling (`TypeError` branch).
- `constants` holding a key `mapping` does not name → that kwarg on the event with its literal value, alongside the resolved ones.
- A path whose leaf is missing **with** a constant of that name → the constant appears on the event, **no** `logger_unresolved_field`, and `logging_handler.failure is False`.
- The same key in both, path resolving → the resolved value wins over the constant.
- `level: error` on a resolvable mapping → the event logs and `logging_handler.failure is True` (the level drives failure, not the resolution).
- `level: nonsense` → `pytest.raises(typer.Exit)` at construction.
- `mapping: { event: "x" }` and, separately, `constants: { event: "x" }` → `pytest.raises(typer.Exit)` at construction.
- `mapping: { exc_info: "x" }` and, separately, `constants: { stack_info: "x" }` → `pytest.raises(typer.Exit)` at construction.
- Any scenario → `expected_emissions={}`; the module never emits.

## Acceptance criteria

- Tests pass.
- One log event per value received, at the configured level and event name, with no output emitted.
- Dict and str `mapping` forms both work; the str form is equivalent to a one-key dict with an empty path.
- Paths resolve through attributes and dict entries alike; an unresolvable one is an ERROR that omits its kwarg and keeps the rest, **unless** `constants` names it, in which case the constant stands silently.
- `constants` keys `mapping` does not name appear on every event; keys it does name are overwritten by a resolved value.
- An invalid `level` or a reserved kwarg (`event`, `exc_info`, `stack_info`) in either dict aborts at construction, before any value is processed.
- `logger` → `LoggerMod` resolves in the manifest.

## Constraints

- **Log only.** No transform of `value`, no output ports, no config beyond the four fields — a node that emitted something would be a different node.
- **Domain-agnostic.** Lives in `modules/funcs.py`, names no `rtl_buddy` type, and is not part of the seven pipeline nodes ([spec 02 Deliverables](02-filelist-extract.md#deliverables)).
- **Config errors abort, item errors defer.** An invalid level or reserved kwarg is `log.fatal` at construction; an unresolvable field with no constant behind it is `log.error` per item. Do not soften the first or escalate the second.
- **A constant silences the ERROR for its own kwarg only** — it is a per-name fallback, never a blanket suppression of `logger_unresolved_field`.
- **`event`, `exc_info`, and `stack_info` are reserved** in both `mapping` and `constants` — validated at construction. `event` collides with the positional event name; `exc_info` and `stack_info` are structlog-meaningful and would be interpreted rather than rendered as fields.
- **One log call per invocation**, built from `constants` overlaid by the resolved mapping — not one call per field.
- `value` keeps **no Python default**: the node exists to receive something, and a default would make the port non-gating for any upstream branch arm ([spec 09](09-flag-gate.md#rejoining-the-arms)).

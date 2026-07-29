# `early-stop-gate`

**Class:** `EarlyStopGateMod` (`modules/rtl_buddy/control.py`)

[Back to index](index.md)

A pass-through gate that short-circuits a test once the run has reached the requested `early_stop` depth. The `test` graph places three instances — after prep (`pre`), after compile (`comp`), and after sim (`sim`) — each configured with its own phase. When `--early-stop` names a depth at or before the gate's phase, the gate emits nothing (ending the pipeline for that test) and logs `test_stopped_early` at `INFO`.

Because its input surface is not fixed (it forwards whatever edges arrive), it uses `**edges`.

## Inputs

| Port | Type | Default | Meaning |
|---|---|---|---|
| `early_stop` | `str` | `"post"` | requested stop depth (CLI `--early-stop`): `pre` / `comp` / `sim` / `post` |
| `**edges` | — | — | all upstream payloads for this key (must include `test`); forwarded when not stopping |

## Config

```yaml
config:
  phase: pre   # "pre" | "comp" | "sim"
```

| Field | Type | Purpose |
|---|---|---|
| `phase` | `str` | this gate's position in the run-depth order; compared against `early_stop` |

## Outputs

When `early_stop`'s depth ≤ this gate's `phase`, the gate emits nothing (the test is stopped). Otherwise every input edge is re-emitted on its own port unchanged.

## Failure routing

An `early_stop` value outside the `RunDepth` order (`pre`/`comp`/`sim`/`post`) is `log.fatal` (`invalid_early_stop`). A stopped test logs `test_stopped_early` at `INFO` (no `log.error`, so `handler.failure` stays `False`).

## Graph nodes

`gate-pre` (`phase: pre`), `gate-comp` (`phase: comp`), `gate-sim` (`phase: sim`), each contract `keyed_join` (`key_field: key`, `persistent_inputs: [early_stop]`). `gate-pre` and `gate-comp` add `unwrap: true`, `ignore: [test]` because they forward a `KeyedValue` edge (`model` and `simv` respectively) — the contract unwraps it in and rewraps it out, so the gate passes bare values through. `gate-sim` forwards only self-keyed payloads (`test` + `proc`) and needs neither.

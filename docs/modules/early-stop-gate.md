# `early-stop-gate`

**Class:** `EarlyStopGateMod` (`modules/rtl_buddy/control.py`)

[Back to index](index.md)

A pass-through gate that short-circuits a test once the run has reached the requested `early_stop` depth. The `test` graph places three instances — after prep (`pre`), after compile (`comp`), and after sim (`sim`) — each configured with its own phase. When `--early-stop` names a depth at or before the gate's phase, the gate emits an `early_stop` `TestResult` instead of forwarding, ending the pipeline for that test at that point.

Because its input surface is not fixed (it forwards whatever edges arrive), it uses `**edges` and declares `output_groups = {"stop": ["stop"], "pass": REST}` — the `stop` port carries the result, and every other emitted port passes through unchanged.

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

`stop` — a `TestResult.early_stop` when `early_stop`'s depth ≤ this gate's `phase`; otherwise every input edge is re-emitted on its own port unchanged.

## Failure routing

An `early_stop` value outside the `RunDepth` order (`pre`/`comp`/`sim`/`post`) is `log.fatal` (`invalid_early_stop`).

## Graph nodes

`gate-pre` (`phase: pre`), `gate-comp` (`phase: comp`), `gate-sim` (`phase: sim`), each contract `keyed_join` (`key_field: key`, `persistent_inputs: [early_stop]`). `gate-pre` and `gate-comp` add `unwrap: true`, `ignore: [test, stop]` because they forward a `KeyedValue` edge (`model` and `simv` respectively) — the contract unwraps it in and rewraps it out, so the gate passes bare values through. `gate-sim` forwards only self-keyed payloads (`test` + `proc`) and needs neither. Each `stop` port fans into [summarise-results](summarise-results.md) (`stop_pre` / `stop_comp` / `stop_sim`).

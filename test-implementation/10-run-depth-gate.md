# Spec 10: RunDepthGate

## What this covers

Implement `RunDepthGate` in `modules/rtl_buddy_compat/preproc.py` (the file created by spec 09). One Python class, three graph node instances configured with different `gate_depth` values. Each instance acts as an early-stop check point in the pipeline.

## Prerequisites

Specs 00 and 09 (artefacts + preproc.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/runner/test_runner.py:L58-L79` — all three `RunDepth` early-stop cases
- `rtl_buddy/src/rtl_buddy/runner/test_results.py:L50-L57` — `EarlyStopResults` shape

## Addition to `modules/rtl_buddy_compat/preproc.py`

### `RunDepthGate`

```
contract: latest, trigger_ports: [payload]
inputs:  root: RootContext, payload: <varies by instance>
outputs: continue → same type as payload
         early_stop → TestResultRow
```

```python
class RunDepthGate:
    class Config:
        gate_depth: str   # "pre", "comp", or "sim"
        stop_desc: str    # desc string for the early-stop result row

    def __init__(self, config: Config):
        self.config = config

    def run(self, root, payload):
        if root.run_depth == self.config.gate_depth:
            return ("early_stop", TestResultRow(
                key=payload.instance_key,
                result="NA",
                desc=self.config.stop_desc,
            ))
        return ("continue", payload)
```

`payload.instance_key` must exist on the payload type. The three payload types (`PreprocessedRunPlan`, `CompileResult`, `LinkedSimArtifacts`) all expose `.instance_key: TestInstanceKey` — confirmed in spec 00.

**Branch termination**: when `early_stop` fires, nothing is emitted on `continue`. When `RunDepthGate` eventually exhausts its input stream and terminates, the harness writes `EndSentinel` to all output ports including `continue`. Nodes downstream of `continue` receive that `EndSentinel` and terminate without processing anything. No explicit termination signal is needed from the module.

The three graph instances and their configs:

| Node ID              | `gate_depth` | `stop_desc`                   |
|----------------------|--------------|-------------------------------|
| `run-depth-gate-pre` | `"pre"`      | `"Stopped early at preproc"`  |
| `run-depth-gate-comp`| `"comp"`     | `"Stopped early at compile"`  |
| `run-depth-gate-sim` | `"sim"`      | `"Stopped early at sim"`      |

Compatibility: `test_runner.py:L58-L61, L68-L70, L77-L79`, `test_results.py:L50-L57`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `preproc.py` entry:

```yaml
  - name: run_depth_gate
    class_name: RunDepthGate
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_run_depth_gate.py`.

Use `PreprocessedRunPlan` as the payload type for all tests (it has `.instance_key`).

- `run_depth="pre"`, `gate_depth="pre"` → emits `("early_stop", ...)` with `result="NA"`
- `run_depth="post"`, `gate_depth="pre"` → emits `("continue", payload)` unchanged
- `run_depth="comp"`, `gate_depth="comp"` → emits `"early_stop"`
- `run_depth="post"`, `gate_depth="comp"` → emits `"continue"`
- `run_depth="sim"`, `gate_depth="sim"` → emits `"early_stop"`
- `stop_desc` appears verbatim in the emitted `TestResultRow.desc`
- `result="NA"` on early stop (not `"FAIL"`)
- Payload is passed through unchanged on `"continue"`

## Constraints

- No type-specific logic for the three payload types. The module must work generically via `payload.instance_key`.
- `result` on early stop is `"NA"`, not `"FAIL"`. Early stop is neither a pass nor a failure in the legacy semantics — it maps to the `EarlyStopResults` class which has its own `is_pass()` returning `False`.

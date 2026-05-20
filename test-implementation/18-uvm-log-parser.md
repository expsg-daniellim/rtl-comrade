# Spec 18: UvmLogParser

## What this covers

Implement `UvmLogParser` in `modules/rtl_buddy_compat/post.py` (the file created by spec 17). This module parses the UVM report summary block from simulation logs and enforces warning/error/fatal thresholds.

## Prerequisites

Specs 00 and 17 (artefacts + post.py file exists) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:L42-L80` — full `UvmVlogPost.get_results()`; exact regex and threshold logic
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L292-L299` — `max_warning` and `max_error` taken from `test_cfg.uvm`

## Addition to `modules/rtl_buddy_compat/post.py`

### `UvmLogParser`

```
contract: default
inputs:  linked: LinkedSimArtifacts
outputs: default → TestResultRow
```

Port `UvmVlogPost.get_results()` from `vlog_post.py:L42-L80`.

Implementation steps:

1. Open `linked.log_path`. On `FileNotFoundError`: emit `result="FAIL"`, `desc="log file not found"`.

2. Search for the UVM report summary block. The block is identified by a recognizable header line — check `vlog_post.py` for the exact regex.

3. If summary absent or unparseable: emit `result="FAIL"`, `desc="UVM report summary not found"`.

4. Extract counts: `UVM_INFO`, `UVM_WARNING`, `UVM_ERROR`, `UVM_FATAL`.

5. Get thresholds from `linked.sim_result.command.test.uvm`:
   - `max_warning = uvm_dict.get("max_warning", 0)`
   - `max_error = uvm_dict.get("max_error", 0)`

6. Pass conditions (all must hold):
   - `UVM_FATAL == 0`
   - `UVM_ERROR <= max_error`
   - `UVM_WARNING <= max_warning`

7. If all pass: emit `result="PASS"`, `desc="UVM: PASS"`.
   Otherwise: emit `result="FAIL"`, `desc` describing the first failing condition.

8. Emit `TestResultRow(key=linked.instance_key, result=result, desc=desc, evidence={"log": linked.log_path})`.

Compatibility: `vlog_post.py:L42-L80`, `vlog_sim.py:L292-L299`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `post.py` entry:

```yaml
  - name: uvm_log_parser
    class_name: UvmLogParser
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_uvm_log_parser.py`.

Write synthetic log files in `tmp_path` that include or omit the UVM summary block. Check `vlog_post.py` for the exact summary format to replicate in test fixtures.

- Valid summary, zero counts → `result="PASS"`
- Valid summary, `UVM_FATAL=1` → `result="FAIL"`
- Valid summary, `UVM_ERROR=1`, `max_error=0` → `result="FAIL"`
- Valid summary, `UVM_ERROR=1`, `max_error=1` → `result="PASS"` (within threshold)
- Valid summary, `UVM_WARNING=3`, `max_warning=2` → `result="FAIL"` (exceeds threshold)
- Valid summary, `UVM_WARNING=3`, `max_warning=5` → `result="PASS"` (within threshold)
- Summary block absent → `result="FAIL"`, desc mentions "not found"
- Missing log file → `result="FAIL"`

## Constraints

- Thresholds must come from `linked.sim_result.command.test.uvm`, not from module config.
- Default threshold for both `max_warning` and `max_error` is `0` when the key is absent from the UVM dict.
- `UVM_FATAL` has no configurable threshold — any fatal count causes failure.

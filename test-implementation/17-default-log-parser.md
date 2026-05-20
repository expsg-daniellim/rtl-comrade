# Spec 17: PostParserSelect + DefaultLogParser

## What this covers

Implement `PostParserSelect` and `DefaultLogParser` in `modules/rtl_buddy_compat/post.py`. `PostParserSelect` is a trivial two-line router; it is grouped here because its only purpose is to gate entry into `DefaultLogParser` or `UvmLogParser`. `UvmLogParser` — the more complex parser — is spec 18.

## Prerequisites

Spec 00 (artefacts) must be complete.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/tools/vlog_post.py:L12-L39` — `VlogPost.get_results()`; exact pattern matching and result override order
- `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:L287-L303` — parser selection logic
- `rtl_buddy/src/rtl_buddy/runner/test_results.py:L10-L31` — result/desc defaulting

## File: `modules/rtl_buddy_compat/post.py`

Create this file. Spec 18 will add `UvmLogParser` to it.

### `PostParserSelect`

```
contract: default
inputs:  linked: LinkedSimArtifacts
outputs: default_parser → LinkedSimArtifacts
         uvm_parser     → LinkedSimArtifacts
```

```python
def run(self, linked):
    if linked.sim_result.command.test.uvm is not None:
        return ("uvm_parser", linked)
    return ("default_parser", linked)
```

Compatibility: `vlog_sim.py:L287-L303`.

---

### `DefaultLogParser`

```
contract: default
inputs:  linked: LinkedSimArtifacts
outputs: default → TestResultRow
```

Port `VlogPost.get_results()` from `vlog_post.py:L12-L39`.

Implementation steps:

1. Open `linked.log_path`. On `FileNotFoundError`: emit `result="NA"`, `desc="log file not found"`.
2. Initialize: `result=None`, `desc=None`.
3. Scan line by line:
   - Match `FAIL` → record
   - Match `ERR` or `FAT` → record
   - Match `PASS` → record (note: checked last in legacy code, so it overrides)
4. Result determination (this order is critical — matches `vlog_post.py:L24-L38`):
   - If fail/err matched: `result="FAIL"`, `desc` from matched text
   - If pass matched: `result="PASS"`, `desc="PASS"` (overrides the fail if both present)
   - If nothing matched: `result="NA"`, `desc="test result unknown"`
5. Emit `TestResultRow(key=linked.instance_key, result=result, desc=desc, evidence={"log": linked.log_path})`.

**Critical**: PASS overrides FAIL when both appear. This is the legacy behavior — the PASS check comes after and overwrites the FAIL state.

Compatibility: `vlog_post.py:L12-L39`, `test_results.py:L10-L31`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Append to `files`:

```yaml
- file: post.py
  plugins:
  - name: post_parser_select
    class_name: PostParserSelect
  - name: default_log_parser
    class_name: DefaultLogParser
```

Spec 18 will add `UvmLogParser` to this entry.

## Tests

Write `modules/rtl_buddy_compat/tests/test_default_log_parser.py`.

**`PostParserSelect`**:
- `test.uvm=None` → emits on `"default_parser"`
- `test.uvm={"max_warning": 0}` → emits on `"uvm_parser"`

**`DefaultLogParser`** (write temp log files with `tmp_path`):
- Log contains only `"PASS"` → `result="PASS"`
- Log contains only `"FAIL"` → `result="FAIL"`
- Log contains both `"PASS"` and `"FAIL"` → `result="PASS"` (PASS overrides)
- Log contains `"ERR"` but no `"PASS"` → `result="FAIL"`
- Log contains `"FAT"` but no `"PASS"` → `result="FAIL"`
- Empty log → `result="NA"`, `desc="test result unknown"`
- Missing log file → `result="NA"` with appropriate desc

Check `vlog_post.py` for exact regex patterns to replicate.

## Constraints

- PASS must override FAIL when both appear — this is intentional legacy behavior, not a bug.
- `PostParserSelect` must have zero filesystem access.

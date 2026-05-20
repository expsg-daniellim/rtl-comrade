# Spec 20: SummaryRender

## What this covers

Implement `SummaryRender` in `modules/rtl_buddy_compat/results.py` (the file created by spec 19). This is the terminal render node; it formats the final summary for stdout.

Exit code is handled by the harness's deferred-failure model — modules that emit a FAIL or NA result row must call `log.error(...)` at that point. The harness exits with code 1 if any `log.error` was called during the run. No separate `ExitCodeResolve` node is needed.

## Prerequisites

Specs 00 and 19 (artefacts + results.py file exists) must be complete.

## Modules responsible for calling `log.error`

Each of the following must call `log.error` when emitting a non-pass result row:

| Module | Condition |
|---|---|
| `RunDepthGate` | emitting on `early_stop` port |
| `CompileExecute` | `returncode != 0` |
| `SeedResolve` | seed resolution failure |
| `SimExecute` | timeout |
| `DefaultLogParser` | parsed result is `FAIL` |
| `UvmLogParser` | parsed result is `FAIL` |
| `RegressionLevelSkipFilter` | result is `SKIP` (pass-like, so **do not** call `log.error` here) |

`SKIP` is pass-like and must not trigger a non-zero exit code.

## Before you start

Read:
- `rtl_buddy/src/rtl_buddy/rtl_buddy.py:L192-L200` — summary render format
- `rtl_buddy/src/rtl_buddy/runner/test_results.py:L28-L29` — pass-like results: `"PASS"` and `"SKIP"`

## Additions to `modules/rtl_buddy_compat/results.py`

### `SummaryRender`

```
contract: unit
inputs:  summary: SuiteResultSummary
outputs: default → RenderedOutput
```

```python
def run(self, summary):
    lines = ["\nTest Results Summary\n"]
    for row in summary.rows:
        lines.append(f"  {row.key.expanded_test_name:<40}  {row.result:<6}  {row.desc}")
    lines.append("")
    return RenderedOutput(text="\n".join(lines))
```

Column widths are approximate — match `rtl_buddy.py:L192-L198` as closely as possible.

Compatibility: `rtl_buddy.py:L192-L198`.

## Register in `modules/rtl_buddy_compat/config.yaml`

Add to the existing `results.py` entry:

```yaml
  - name: summary_render
    class_name: SummaryRender
```

## Tests

Write `modules/rtl_buddy_compat/tests/test_summary_render.py`.

**`SummaryRender`**:
- Output starts with `"\nTest Results Summary\n"`
- Two rows → both test names and results present in output
- `result="PASS"` appears in rendered text
- Empty `rows` → output still starts with `"\nTest Results Summary\n"` and ends with an empty line

## Constraints

- `"SKIP"` is pass-like and must not trigger `log.error`.
- `"FAIL"` and `"NA"` must trigger `log.error` in the emitting module, not here.
- `SummaryRender` is purely a formatter — it must not branch on result values or set any global state.

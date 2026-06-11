# Spec 09: Post-processing modules (index)

**Depends on:** spec 01 (schema), spec [01b](01b-suite-schema.md) (`RoutePostMod`
reads `ctx["test"].uvm`; `ParseUvmLogMod` reads `ctx["test"].uvm.max_warns` /
`.max_errors` — `UVMConfig` lives in 01b).
**References:** [03 — Post-processing section](../03-module-catalog.md), [07 settled 14, 15](../07-ambiguities-and-assumptions.md).

## Goal

Implement the log-parse trio: a uvm/plain classifier router and two atomic parsers.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_test/sim.py` (continuing from spec 08); tests in
`modules/tests/test_post.py`.

| Ticket | Module | What it does |
|---|---|---|
| [09a](09a-route-post.md) | `RoutePostMod` | Route uvm vs plain. |
| [09b](09b-parse-log.md) | `ParseLogMod` | Parse a plain sim log → `TestResults`. |
| [09c](09c-parse-uvm-log.md) | `ParseUvmLogMod` | Parse a UVM Report Summary → `TestResults`. |

**Manifest** — these three modules append to the `rtl_test/sim.py` block in `modules/config.yaml`
opened by the sim chain ([`08a`](08a-expand-runs.md)):

```yaml
  - { name: route-post,    class_name: RoutePostMod }
  - { name: parse-log,     class_name: ParseLogMod }
  - { name: parse-uvm-log, class_name: ParseUvmLogMod }
```

## Acceptance criteria

- Each child ticket's tests pass.
- `ParseUvmLogMod`: fixture-by-fixture comparison against rtl_buddy `UvmVlogPost` on the
  same log files produces identical `TestResults`.
- `ParseLogMod`: identical to rtl_buddy `VlogPost` on clean-PASS, clean-FAIL-with-ERR,
  and NA fixtures; intentionally diverges on FAIL+PASS, FAIL-without-ERR, and
  word-boundary cases — see [07 settled 15](../07-ambiguities-and-assumptions.md).

## Notes

`route-post` + two-parsers is the example I keep returning to for "atomic-by-function,
not by signature" — make sure the implementation preserves that split rather than
collapsing them back into one node.

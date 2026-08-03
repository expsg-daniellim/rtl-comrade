# idx-09 — Post-processing modules (group index)

> Navigation only — not a build ticket. The buildable units are the child specs under [`specs/`](specs/).

**Depends on:** spec 01 (schema), spec [01b](specs/01b-suite-schema.md) (`RoutePostMod`
reads `test.uvm`; `ParseUvmLogMod` reads `test.uvm.max_warns` /
`.max_errors` — `UVMConfig` lives in 01b).
**References:** [03 — Post-processing section](03-module-catalog.md), [07 settled 14, 15](07-ambiguities-and-assumptions.md).

## Goal

Implement the log-parse trio: a uvm/plain classifier router and two atomic parsers.

This spec is split into one ticket per module — build them as independent units. All live
in `modules/rtl_buddy/sim.py` (continuing from spec 08); tests in
`modules/tests/test_post.py`.

| Ticket | Module | What it does |
|---|---|---|
| [09a](specs/09a-route-post.md) | `RoutePostMod` | Route uvm vs plain. |
| [09b](specs/09b-parse-log.md) | `ParseLogMod` | Parse a plain sim log → `TestResult`. |
| [09c](specs/09c-parse-uvm-log.md) | `ParseUvmLogMod` | Parse a UVM Report Summary → `TestResult`. |

**Manifest** — these three modules append to the `rtl_buddy/sim.py` block in `modules/config.yaml`
opened by the sim chain ([`08a`](specs/08a-expand-runs.md)):

```yaml
  - { name: route-post,    class_name: RoutePostMod }
  - { name: parse-log,     class_name: ParseLogMod }
  - { name: parse-uvm-log, class_name: ParseUvmLogMod }
```

## Acceptance criteria

- Each child ticket's tests pass.
- Integration coverage lives in the child tickets' own acceptance criteria (`route-post`
  `uvm`/`plain` routing, `UvmVlogPost`/`VlogPost` fixture parity, and the documented
  `ParseLogMod` divergences); the post leg is wired and exercised end-to-end in
  [spec 11](specs/11-graph-and-manifests.md) and [spec 12](specs/12-end-to-end.md).
- Every child's `modules/config.yaml` entry validates and resolves: `route-post` →
  `RoutePostMod`, `parse-log` → `ParseLogMod`, `parse-uvm-log` → `ParseUvmLogMod` (see
  [11](specs/11-graph-and-manifests.md#acceptance-criteria)).

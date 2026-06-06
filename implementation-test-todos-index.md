# Implementation-test todos — index

Quick reference. See `implementation-test-todos.md` for full detail on any item.

## Design-level

| # | Title | Status |
|---|---|---|
| 1 | Enumerate failure modes — and resolve open questions sitting in build tickets | Resolved 2026-05-31 |
| 2 | Integrate graph failures with `log.fatal` / `log.error` | Resolved 2026-05-31 |
| 3 | Define the interim strategy for parallel runs | Resolved 2026-05-31 |
| 4 | Specify and validate the `any` contract and `fan-in-results` module | Resolved 2026-06-05 |
| 5 | Finalise `run-process` async + signal semantics | Resolved 2026-05-31 |
| 6 | Document framework-verification contingencies | Resolved 2026-06-02 |
| 7 | Pin the interim CWD strategy | Resolved 2026-06-02 |
| 8 | Prepend `.` to `$PATH` for CWD-local tool discovery | Resolved 2026-06-02 |
| 9 | Define the `builder_cfg` / `RtlBuilderConfig` schema | Resolved 2026-06-02 |
| 10 | Pin the `tests.yaml` and `models.yaml` schemas | Resolved 2026-06-02 |
| 11 | Verify persistent-but-unwired CLI defaults | Resolved 2026-06-02 |
| 12 | Specify `logs/` directory ownership and lifecycle | Resolved 2026-06-02 |
| 13 | Decide `VlogPost` quirks — replicate or fix | Resolved 2026-06-05 |
| 14 | Confirm sibling-graph scope (resolve `07` item 16) | Resolved 2026-06-05 |
| 15 | Add a `git-status` equivalent — or explicitly de-scope it | **Open** |
| 30 | Validate the interim parallel-safety shim added by TODO #3 | **Open** |

## Spec polish

| # | Title | Status |
|---|---|---|
| 16 | Strengthen source traceability to rtl_buddy | **Open** |
| 17 | Split grouped module specs into per-module tickets | **Open** |
| 18 | Include module code skeletons inside the spec | **Open** |
| 19 | Inline the I/O surface block in every module spec | **Open** |
| 20 | Add a "Before you start" reading list to every spec | **Open** |
| 21 | Inline file path and manifest entries in each spec | **Open** |
| 22 | Expand each module's algorithm into numbered implementation steps | **Open** |
| 23 | Add a "Constraints" section to every spec | **Open** |
| 24 | Enumerate test cases with input/expected pairs | **Open** |
| 25 | Spell out filename and format placeholders | **Open** |
| 26 | Add forward-reference notes between specs that share a file | **Open** |
| 27 | Expand "Acceptance criteria" to enumerate observable behaviour | **Open** |

## Cosmetic

| # | Title | Status |
|---|---|---|
| 28 | Pin the module file-layout and package conventions | **Open** |
| 29 | Clarify the dataflow diagram | **Open** |

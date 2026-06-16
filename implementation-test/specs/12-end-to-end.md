# Spec 12: End-to-end validation

**Depends on:** spec 11.
**References:** [07 — Notable divergences](../07-ambiguities-and-assumptions.md), `rtl_buddy/AGENTS.md` validation section.

## Before you start

Read `docs/running.md` for the invocation syntax this validation drives (`rtl-comrade test` vs
the reference `rtl_buddy test`) and `docs/testing.md` for the conventions the committed e2e
artifacts under `tests/` must follow. The reference suite and validation procedure are in
`rtl_buddy/AGENTS.md` (validation section), already named in **References** above. This spec
depends on the assembled graph from [`spec 11`](11-graph-and-manifests.md); there are no
file-sharing siblings.

## Goal

Validate the assembled `test` graph end-to-end against a real rtl_buddy suite, confirming
behaviour parity with `rtl_buddy test` on the cases the design promises to preserve, and
documenting any divergences observed.

## Deliverables

- A walkthrough validating against `../rtl-buddy-proj-template/design/sandbox/verif`
  (per `rtl_buddy/AGENTS.md`), comparing:
  - `cd verif && rtl_buddy test basic` (reference)
  - `cd verif && rtl-comrade test basic` (the new graph)
- Captured artifacts (committed under `tests/e2e/` or similar):
  - exit code parity for passing run, compile-fail, sim-timeout, and `--list`. For
    `--early-stop` at each phase, assert Plan B exits **0** (deliberate divergence — rtl_buddy
    exits 1; [07 — Notable divergences](../07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)),
    while per-test `NA` + `desc` still match.
  - summary string fidelity (allow formatting differences; assert per-test PASS/FAIL/NA
    and `desc` match).
  - artifact parity in `logs/`: `.log`, `.err`, `.randseed` produced for the same runs;
    the `test.*` symlinks (`test.log` / `test.err` / `test.randseed`, in CWD; spec
    [08e](08e-link-latest.md)) point to the same files.
- A `KNOWN_DIVERGENCES.md` (or new section in [07](../07-ambiguities-and-assumptions.md))
  recording any behavioural deltas discovered that were not anticipated by the plan.

## Tests

End-to-end parity scenarios, each driving `cd verif && rtl-comrade test …` against the real
reference suite `../rtl-buddy-proj-template/design/sandbox/verif` and comparing to `rtl_buddy
test …`. The input is a CLI invocation; the expected output is parity (exit code + per-test
PASS/FAIL/NA + `desc`) with the reference, plus the named artifacts. Captured artifacts are
committed under `tests/e2e/`; summary-string **formatting** differences are allowed, per-test
verdicts are not.

- `rtl-comrade test <passing-test>` → exit `0`, per-test `PASS` matching `rtl_buddy`; `logs/`
  carries `.log`/`.err`/`.randseed` for the run and the `test.*` symlinks point at the same
  files (artifact parity).
- `rtl-comrade test <compile-fail-test>` → non-zero exit and per-test `FAIL` parity; the
  compile log is persisted (new behaviour, [07 settled 12](../07-ambiguities-and-assumptions.md)).
- `rtl-comrade test <sim-timeout-test>` → non-zero exit and the SimTimeout verdict parity
  (the `rc=4444`/`timed_out` path), matching `rtl_buddy`.
- `rtl-comrade test --list` → prints the suite's test names in declaration order, exit `0`,
  matching `rtl_buddy test --list`.
- `rtl-comrade test --early-stop <phase>` for each phase (`pre`/`comp`/`sim`) → exit **0**
  (deliberate divergence — rtl_buddy exits 1; [07 — Notable divergences](../07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy))
  with per-test `NA` "Stopped early at <phase>" + `desc` parity; one `test_result` per stopped
  test (boundary: all three phases).
- **Lazy load-model** — a suite where a *skipped* test references a broken `models.yaml` →
  the run completes and the skipped test does not trip on the broken model (new behaviour,
  [07 settled 8](../07-ambiguities-and-assumptions.md)).
- **ParseLog corrections** — logs exercising FAIL-wins-over-PASS, a `PASSTHROUGH` line, and a
  FAIL-without-`ERR:` line → verdicts match the corrected behaviour, no crash
  ([07 settled 15](../07-ambiguities-and-assumptions.md)).
- **Concurrency divergence (expected)** — scenarios that collide on shared-CWD artefacts are
  run sequentially or recorded as KIV in `KNOWN_DIVERGENCES.md`; parity is **not** forced with
  a serialising lock (boundary: known divergence until [07 item 17](../07-ambiguities-and-assumptions.md)).

## Acceptance criteria

- All five parity scenarios run against the reference suite
  `../rtl-buddy-proj-template/design/sandbox/verif` (per `rtl_buddy/AGENTS.md`). Four match
  `rtl_buddy` on exit code and per-test PASS/FAIL/NA + `desc`: passing run, compile-fail,
  sim-timeout, and `--list`. `--early-stop` at each phase (`pre`/`comp`/`sim`) matches per-test
  `NA` + `desc` but **diverges on exit code** — Plan B exits 0 where rtl_buddy exits 1
  ([07 — Notable divergences](../07-ambiguities-and-assumptions.md#notable-divergences-from-rtl_buddy)).
- Artifact parity in `logs/`: `.log`/`.err`/`.randseed` produced for the same runs and the
  `test.log`/`test.err`/`test.randseed` symlinks (in CWD) point at the same files; compile
  logs are persisted (new behaviour, [07 settled 12](../07-ambiguities-and-assumptions.md)).
- Lazy `load-model` behaves correctly: skipped tests don't trip on broken `models.yaml`
  (the new behaviour from [07 settled 8](../07-ambiguities-and-assumptions.md)).
- `ParseLogMod` quirk corrections verified: FAIL wins over PASS, `PASSTHROUGH` does not
  misclassify as PASS, FAIL-without-ERR does not crash — per
  [07 settled 15](../07-ambiguities-and-assumptions.md).
- The captured artifacts are committed under `tests/e2e/`, and any unexpected divergence is
  recorded in `KNOWN_DIVERGENCES.md` (or [07](../07-ambiguities-and-assumptions.md)) with a
  follow-up issue opened.

## Constraints

- Validate against the real reference suite `../rtl-buddy-proj-template/design/sandbox/verif`
  (per `rtl_buddy/AGENTS.md`) — do not substitute a synthetic fixture for the parity claims.
- Assert **exit-code** and **per-test PASS/FAIL/NA + `desc`** parity for the four full-parity
  scenarios (passing run, compile-fail, sim-timeout, `--list`). For `--early-stop` per phase,
  assert per-test `NA` + `desc` parity but exit **0** (the documented exit-code divergence, not
  parity). Summary-string **formatting** differences are allowed; the per-test verdicts are not.
- Commit the captured artifacts under `tests/e2e/` (or similar), and record any unanticipated
  delta in `KNOWN_DIVERGENCES.md` / [07](../07-ambiguities-and-assumptions.md) with a follow-up
  issue.
- Concurrency divergences are **expected** until [07 item 17](../07-ambiguities-and-assumptions.md)
  lands — run sequentially or document the affected scenarios as KIV. Do **not** reintroduce a
  serialising lock to force parity.

## Notes

Concurrency-related divergences are *expected* until the upstream rtl_buddy
per-invocation-subdir change lands ([07 KIV 17](../07-ambiguities-and-assumptions.md));
either run this validation with sequential semantics (configure a concurrency-limiting
contract, or wait for upstream) or document the affected scenarios as KIV.

Once this spec is signed off, the sibling graphs from [08](../08-sibling-graphs.md) become
the natural next ticket.

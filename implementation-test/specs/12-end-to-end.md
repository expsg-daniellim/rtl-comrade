# Spec 12: End-to-end validation

**Depends on:** spec 11.
**References:** [07 — Notable divergences](../07-ambiguities-and-assumptions.md), `rtl_buddy/AGENTS.md` validation section.

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
  - exit code parity for passing run, compile-fail, sim-timeout, `--list`, `--early-stop`
    at each phase.
  - summary string fidelity (allow formatting differences; assert per-test PASS/FAIL/NA
    and `desc` match).
  - artifact parity in `logs/`: `.log`, `.err`, `.randseed` produced for the same runs;
    `test.*` symlinks point to the same files.
- A `KNOWN_DIVERGENCES.md` (or new section in [07](../07-ambiguities-and-assumptions.md))
  recording any behavioural deltas discovered that were not anticipated by the plan.

## Acceptance criteria

- All five scenarios above match rtl_buddy on exit code and per-test PASS/FAIL/NA.
- Compile logs are persisted as expected (the new behaviour from [07 settled 12](../07-ambiguities-and-assumptions.md)).
- Lazy `load-model` behaves correctly: skipped tests don't trip on broken `models.yaml`
  (the new behaviour from [07 settled 8](../07-ambiguities-and-assumptions.md)).
- `ParseLogMod` quirk corrections verified: FAIL wins over PASS, `PASSTHROUGH` does not
  misclassify as PASS, FAIL-without-ERR does not crash — per
  [07 settled 15](../07-ambiguities-and-assumptions.md).
- Any unexpected divergence is documented and a follow-up issue opened.

## Notes

Concurrency-related divergences are *expected* until the upstream rtl_buddy
per-invocation-subdir change lands ([07 KIV 17](../07-ambiguities-and-assumptions.md));
either run this validation with sequential semantics (configure a concurrency-limiting
contract, or wait for upstream) or document the affected scenarios as KIV.

Once this spec is signed off, the sibling graphs from [08](../08-sibling-graphs.md) become
the natural next ticket.

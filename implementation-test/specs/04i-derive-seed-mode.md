# Spec 04i: derive-seed-mode (`DeriveSeedModeMod`)

**Depends on:** spec 01 (schema — `SeedMode`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Goal

Derive the `SeedMode` from the two CLI booleans — the trivial seed-mode classifier.

## Deliverables

In `modules/rtl_test/setup.py`:

- `DeriveSeedModeMod` — `(rnd_new:bool=False, rnd_last:bool=False)` → `SeedMode` (`rnd_new`
  wins, else `REPLAY` if `rnd_last`, else `DEFAULT`). No failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:188-194` — the seed-mode block in `do_cmd_test`; enum at `seed_mode.py:4-7`.

Manifest entries in `modules/config.yaml` per [06 — Manifest additions](../06-graph-yaml.md).

## Tests

In `modules/tests/test_setup.py`:

- `(rnd_new=True, rnd_last=True)` → `NEW` (rnd_new wins).
- `(rnd_new=False, rnd_last=True)` → `REPLAY`.
- `(rnd_new=False, rnd_last=False)` → `DEFAULT`.

## Acceptance criteria

- Tests pass.
- Maps the two CLI booleans to the correct `SeedMode` for all three precedence cases
  (contributes to the setup-only end-to-end graph — see
  [04 index](04-setup-modules.md#acceptance-criteria)).

## Notes

`DeriveSeedModeMod` is on the KIV path (item 18) — keep it small and stateless; future
absorbing into `resolve-seed` should be straightforward.

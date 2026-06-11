# Spec 04i: derive-seed-mode (`DeriveSeedModeMod`)

**Depends on:** spec 01 (schema — `SeedMode`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_test/setup.py`, shared with the setup chain
(`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`,
index [05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared
imports and helpers with those specs.

## Goal

Derive the `SeedMode` from the two CLI booleans — the trivial seed-mode classifier.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   rnd_new:bool = False, rnd_last:bool = False
outputs:  default → SeedMode
```

```python
class DeriveSeedModeMod:
    def run(self, rnd_new:bool = False, rnd_last:bool = False):
        mode = SeedMode.DEFAULT
        if rnd_new:
            mode = SeedMode.NEW
        elif rnd_last:
            mode = SeedMode.REPLAY
        return ("default", mode)
```

## Deliverables

In `modules/rtl_test/setup.py`:

- `DeriveSeedModeMod` — `(rnd_new:bool=False, rnd_last:bool=False)` → `SeedMode` (`rnd_new`
  wins, else `REPLAY` if `rnd_last`, else `DEFAULT`). No failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:188-194` — the seed-mode block in `do_cmd_test`; enum at `seed_mode.py:4-7`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: derive-seed-mode, class_name: DeriveSeedModeMod }
```

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

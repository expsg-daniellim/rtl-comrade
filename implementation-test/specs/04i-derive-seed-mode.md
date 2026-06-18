# Spec 04i: derive-seed-mode (`DeriveSeedModeMod`)

**Depends on:** spec 01 (schema — `SeedMode`).
**References:** [03 — Setup section](../03-module-catalog.md). Parent index:
[idx-04 — Setup modules](../idx-04-setup.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain
(`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

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

## Algorithm

1. Default `mode = SeedMode.DEFAULT`.
2. If `rnd_new`, set `SeedMode.NEW` (highest precedence); else if `rnd_last`, set
   `SeedMode.REPLAY`.
3. Emit `("default", mode)`. No failure path.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `DeriveSeedModeMod` — `(rnd_new:bool=False, rnd_last:bool=False)` → `SeedMode` (`rnd_new`
  wins, else `REPLAY` if `rnd_last`, else `DEFAULT`). No failure path.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/rtl_buddy.py:188-194` — the seed-mode block in `do_cmd_test`; enum at `seed_mode.py:4-7`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: derive-seed-mode, class_name: DeriveSeedModeMod }
```

## Tests

In `modules/tests/test_setup.py`. Pure function — no fixtures needed.

- `(rnd_new=True, rnd_last=True)` → emits `("default", SeedMode.NEW)` (`rnd_new` wins over
  `rnd_last`).
- `(rnd_new=True, rnd_last=False)` → emits `("default", SeedMode.NEW)`.
- `(rnd_new=False, rnd_last=True)` → emits `("default", SeedMode.REPLAY)`.
- `(rnd_new=False, rnd_last=False)` → emits `("default", SeedMode.DEFAULT)`.
- `()` (both args defaulted) → emits `("default", SeedMode.DEFAULT)` (boundary: default call).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: maps the two CLI booleans to the correct `SeedMode` for
  all three precedence cases.
- No failure path: every input pair maps to a `SeedMode`; the module never logs an error.
- The `modules/config.yaml` manifest entry `{ name: derive-seed-mode, class_name: DeriveSeedModeMod }`
  validates and the harness resolves `derive-seed-mode` → `DeriveSeedModeMod`.

## Constraints

- `unit` contract; emit the `SeedMode` on the string-literal `default` port.
- Precedence is fixed: `rnd_new` → `NEW` (wins); else `rnd_last` → `REPLAY`; else `DEFAULT`.
- No failure path — both inputs are booleans with `False` defaults.
- Keep it small and stateless (KIV item 18 may later absorb it into `resolve-seed`).

## Notes

`DeriveSeedModeMod` is on the KIV path (item 18) — keep it small and stateless; future
absorbing into `resolve-seed` should be straightforward.

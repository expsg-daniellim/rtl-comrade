# Spec 04f: check-suite-cwd (`CheckSuiteCwdMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md),
[01 — Where to invoke `rtl-comrade test` from](../01-cli-and-entry.md). Parent index:
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

Enforce the user-driven CWD convention: `rtl-comrade test` / `randtest` must be invoked
from the suite directory. Resolve the CLI `test_config` against CWD and abort early if it
points elsewhere; emit the resolved `Path` for downstream `parse-suite-config`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   test_config:str = "tests.yaml"
outputs:  default → Path   (resolved suite-config path)
```

```python
class CheckSuiteCwdMod:
    def run(self, test_config:str = "tests.yaml"):
        resolved = (Path.cwd() / test_config).resolve()
        if resolved.parent != Path.cwd().resolve():
            log.critical("suite_cwd_mismatch", test_config=test_config, resolved=str(resolved))
        if not resolved.is_file():
            log.critical("suite_config_missing", test_config=test_config, resolved=str(resolved))
        return ("default", resolved)
```

## Deliverables

In `modules/rtl_test/setup.py`:

- `CheckSuiteCwdMod` — validates the user-driven CWD convention: `rtl-comrade test` /
  `randtest` must be invoked from the suite directory (matching rtl_buddy's `do_cmd_test`,
  which never `chdir`s — see `rtl_buddy/AGENTS.md` validation example: `cd .../verif &&
  python -m rtl_buddy test basic`). Takes the CLI `test_config:str` and resolves it
  against CWD; emits the resolved `Path` that downstream `ParseSuiteConfigMod` consumes.
  **Behaviour**:
  1. `resolved = (Path.cwd() / test_config).resolve()`; `cwd = Path.cwd().resolve()`.
  2. If `resolved.parent != cwd` → `log.critical(f"test_config {test_config!r} resolves
     to {resolved}, which is not in the current directory ({cwd}). Run rtl-comrade test
     from the suite directory.")` — catches `-c /abs/elsewhere/tests.yaml`,
     `-c ../sibling/tests.yaml`, and `-c subdir/tests.yaml`, which would otherwise parse
     fine but silently mistarget `logs/`, `run.f`, `obj_dir_<tag>/`, and the `test.*`
     symlinks to the wrong directory.
  3. If `not resolved.is_file()` → `log.critical(f"test_config {test_config!r} not found
     at {resolved}")`.
  4. Emit `resolved` on `default`.
  Both `.resolve()` calls follow symlinks symmetrically, so a `tests.yaml` symlink in a
  symlinked CWD passes correctly.
  **Failure handling**: both checks are setup-domain config errors → `log.critical` (see
  [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site)).
  **Compatibility source:** no direct rtl_buddy analogue (new check, Notable divergence) — enforces the convention `do_cmd_test` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:166-209`) assumes vs `do_rtl_regression`'s `os.chdir` at `rtl_buddy.py:404`.

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: check-suite-cwd, class_name: CheckSuiteCwdMod }
```

## Tests

In `modules/tests/test_setup.py`:

- `tests.yaml` in CWD → emits resolved Path; bare filename matching
  `Path.cwd() / "tests.yaml"`.
- `-c /abs/elsewhere/tests.yaml` → `log.critical` with CWD-mismatch message.
- `-c ../sibling/tests.yaml` → `log.critical` (parent is not CWD).
- `-c subdir/tests.yaml` → `log.critical` (parent is a subdir of CWD, not CWD).
- Missing file in CWD → `log.critical` with not-found message.
- CWD itself is a symlink (e.g., `/tmp/link → /tmp/real`) and `tests.yaml` sits in
  `/tmp/real` → passes (both `.resolve()` calls collapse to the same realpath).

## Acceptance criteria

- Tests pass.
- `CheckSuiteCwdMod` aborts fixture runs invoked from outside the suite directory and
  emits the resolved `Path` otherwise (contributes to the setup-only end-to-end graph —
  see [04 index](04-setup-modules.md#acceptance-criteria)).

## Notes

`CheckSuiteCwdMod` is the explicit enforcement of the user-driven CWD convention
documented in [01](../01-cli-and-entry.md) — the regression graph does **not** wire it
(regression `chdir`s per-suite internally; see [08](../08-sibling-graphs.md)).

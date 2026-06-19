# Spec 04f: check-suite-cwd (`CheckSuiteCwdMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md), [01 — Where to invoke `rtl-comrade test` from](../01-cli-and-entry.md). Parent index: [idx-04 — Setup modules](../idx-04-setup.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)` signature, the allowed output forms (plain return / named-port tuple / generator), the `finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py` are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit `a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec [`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the setup chain (`04a`–`04i`, index [idx-04](../idx-04-setup.md)), the selection/expansion chain (`05a`–`05f`, index [idx-05](../idx-05-selection-expansion.md)), and git-status (`10b`); coordinate shared imports and helpers with those specs.

## Goal

Enforce the user-driven CWD convention: `rtl-comrade test` / `randtest` must be invoked from the suite directory. Resolve the CLI `test_config` against CWD and abort early if it points elsewhere; emit the resolved suite-config `Path` for `parse-suite-config` **and** the validated **base directory** (`work_dir`) that downstream artefact writers root against. This node is the single source of artefact-location policy — leaf modules consume a resolved path rather than re-deriving it from the ambient CWD (see [Notes](#notes)).

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry — the catalog is the design view, this is the build view; update both when behaviour changes.

```
contract: unit
inputs:   test_config:str = "tests.yaml"
outputs:  default  → Path   (resolved suite-config path → parse-suite-config)
          work_dir → Path   (validated base directory → ensure-logs-dir, write-filelist, build-compile-cmd)
```

```python
class CheckSuiteCwdMod:
    def run(self, test_config:str = "tests.yaml"):
        resolved = (Path.cwd() / test_config).resolve()
        if resolved.parent != Path.cwd().resolve():
            log.fatal("suite_cwd_mismatch", test_config=test_config, resolved=str(resolved))
        if not resolved.is_file():
            log.fatal("suite_config_missing", test_config=test_config, resolved=str(resolved))
        yield ("default", resolved)            # resolved suite-config path → parse-suite-config
        yield ("work_dir", resolved.parent)    # validated base dir (artefact root) → ensure-logs-dir / write-filelist / build-compile-cmd
```

## Algorithm

1. Resolve the configured path against CWD: `resolved = (Path.cwd() / test_config).resolve()` and `cwd = Path.cwd().resolve()`. Both `.resolve()` calls follow symlinks symmetrically, so a `tests.yaml` symlink inside a symlinked CWD still compares equal.
2. **Failure — outside the suite dir.** If `resolved.parent != cwd`: `log.fatal(f"test_config {test_config!r} resolves to {resolved}, which is not in the current directory ({cwd}). Run rtl-comrade test from the suite directory.")` — catches `-c /abs/elsewhere/tests.yaml`, `-c ../sibling/tests.yaml`, and `-c subdir/tests.yaml`, which would otherwise parse but silently mistarget `logs/`, `run.f`, `obj_dir_<tag>/`, and the `test.*` symlinks.
3. **Failure — missing file.** If `not resolved.is_file()`: `log.fatal(f"test_config {test_config!r} not found at {resolved}")`.
4. Emit both ports in lockstep: `("default", resolved)` for `parse-suite-config`, and `("work_dir", resolved.parent)` — the validated base directory — for `ensure-logs-dir`. `work_dir` is the **one** place artefact location is decided: today it is the suite dir (= CWD, since step 2 has just asserted that), but relocating artefacts later (e.g. a `--work-dir` flag) is a change to this node alone, not to every downstream writer.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `CheckSuiteCwdMod` — validates the user-driven CWD convention: `rtl-comrade test` / `randtest` must be invoked from the suite directory (matching rtl_buddy's `do_cmd_test`, which never `chdir`s — see `rtl_buddy/AGENTS.md` validation example: `cd .../verif && python -m rtl_buddy test basic`). Takes the CLI `test_config:str` and resolves it against CWD; emits the resolved suite-config `Path` that downstream `ParseSuiteConfigMod` consumes, **and** the validated base directory `work_dir` (= `resolved.parent`) that `EnsureLogsDirMod` roots the artefact tree against. See [Algorithm](#algorithm) for the numbered steps (resolve → CWD-mismatch check → missing-file check → emit both ports). Both `.resolve()` calls follow symlinks symmetrically, so a `tests.yaml` symlink in a symlinked CWD passes correctly.
  **Failure handling**: both checks are setup-domain config errors → `log.fatal` (see [05 — Log idioms](../05-branching-and-results.md#log-idioms-per-failure-site)).
  **Compatibility source:** no direct rtl_buddy analogue (new check, Notable divergence) — enforces the convention `do_cmd_test` (`rtl_buddy/src/rtl_buddy/rtl_buddy.py:166-209`) assumes vs `do_rtl_regression`'s `os.chdir` at `rtl_buddy.py:404`.

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml` (opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: check-suite-cwd, class_name: CheckSuiteCwdMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `tmp_path` + `monkeypatch.chdir` to set CWD and lay out the (mis)placed files/symlinks; `logging_handler` for the `log.fatal` paths.

- `test_config="tests.yaml"` with the file present in CWD → emits `("default", resolved)` where `resolved == (Path.cwd() / "tests.yaml").resolve()`, **and** `("work_dir", resolved.parent)` where `resolved.parent == Path.cwd().resolve()`.
- `test_config="/abs/elsewhere/tests.yaml"` (absolute, outside CWD) → CWD-mismatch `log.fatal` → `pytest.raises(typer.Exit)`.
- `test_config="../sibling/tests.yaml"` → resolved parent is not CWD → CWD-mismatch `log.fatal` → `pytest.raises(typer.Exit)`.
- `test_config="subdir/tests.yaml"` → resolved parent is a subdir of CWD, not CWD → CWD-mismatch `log.fatal` → `pytest.raises(typer.Exit)`.
- `test_config="tests.yaml"` with no such file in CWD → missing-file `log.fatal` → `pytest.raises(typer.Exit)`.
- CWD is itself a symlink (`/tmp/link → /tmp/real`) and `tests.yaml` sits in `/tmp/real` → emits `("default", resolved)` (boundary: both `.resolve()` calls collapse to the same realpath, so a symlinked CWD still passes).

## Acceptance criteria

- Tests pass.
- Output ports exercised: `default` emits the resolved suite-config `Path` and `work_dir` emits the validated base directory when invoked from the suite directory.
- Failure idioms exercised: invoked from outside the suite dir → `log.fatal` (harness exit 1); the resolved `test_config` not a file → `log.fatal`.
- The `modules/config.yaml` manifest entry `{ name: check-suite-cwd, class_name: CheckSuiteCwdMod }` validates and the harness resolves `check-suite-cwd` → `CheckSuiteCwdMod`.

## Constraints

- `unit` contract; emit the resolved suite-config `Path` on the string-literal `default` port and the validated base directory (`resolved.parent`) on the `work_dir` port (both in lockstep via the generator). Do **not** re-derive the base dir downstream — `work_dir` is the single artefact-location source consumed by `ensure-logs-dir`, `write-filelist`, and `build-compile-cmd`.
- Resolve **both** sides with `.resolve()` (`(Path.cwd() / test_config).resolve()` and `Path.cwd().resolve()`) so symlinks collapse symmetrically — do not compare un-resolved paths.
- Both failures — `resolved.parent != cwd` (outside the suite dir) and `not resolved.is_file()` (missing) — are setup-domain config errors → `log.fatal` (harness exit 1), never a port-routed result.
- Do **not** wire this node in the regression graph (it `chdir`s per-suite); it is `test`/ `randtest` only.

## Notes

`CheckSuiteCwdMod` is the explicit enforcement of the user-driven CWD convention documented in [01](../01-cli-and-entry.md) — the regression graph does **not** wire it (regression `chdir`s per-suite internally; see [08](../08-sibling-graphs.md)).

It is also the **artefact-location provider**: `work_dir` is the one node that decides where outputs live. It fans out directly to `ensure-logs-dir` (which sub-roots `logs/` and feeds the resolved dir to `build-sim-cmd` / `resolve-seed` and `build-compile-cmd`'s log paths), `write-filelist` (which roots `run.<tag>.f` on it), and `build-compile-cmd` (which roots `obj_dir_<tag>/` on it). Every such writer consumes a resolved directory and never touches the ambient process CWD itself. This keeps the rtl_buddy "everything is CWD-relative" assumption out of the leaf modules: relocating artefacts (a future `--work-dir`, or regression's per-suite root) changes this provider alone. In the regression graph the equivalent base-dir source is the per-suite `chdir` context in [08](../08-sibling-graphs.md).

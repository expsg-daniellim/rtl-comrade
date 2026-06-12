# Spec 04g: ensure-logs-dir (`EnsureLogsDirMod`)

**Depends on:** spec 01 (schema).
**References:** [03 — Setup section](../03-module-catalog.md),
[07 settled 25 / 26](../07-ambiguities-and-assumptions.md). Parent index:
[04 — Setup modules](04-setup-modules.md).

## Before you start

Read `docs/modules/implementation.md` — how the harness infers input ports from the `run(...)`
signature, the allowed output forms (plain return / named-port tuple / generator), the
`finalise()` teardown hook, and config-bearing modules; `modules/io.py` and `modules/funcs.py`
are the shipped examples. Open the rtl_buddy source named in the **Compatibility source** entry
below before writing the body (every citation is anchored to rtl_buddy `v1.4.0`, commit
`a69d962`). This module appends to `modules/rtl_buddy/setup.py`, which is created by spec
[`04a`](04a-discover-config-file.md) — append, do not overwrite. The file is shared with the
setup chain (`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain
(`05a`–`05f`, index [05](05-selection-expansion-modules.md)), and git-status (`10b`);
coordinate shared imports and helpers with those specs.

## Goal

Bootstrap the CWD-relative artefact directory (`logs/` by default) once at startup, ahead
of any subprocess, so no downstream writer needs its own `mkdir`.

## Surface

I/O surface and skeleton, mirrored from the [03 catalog](../03-module-catalog.md) entry —
the catalog is the design view, this is the build view; update both when behaviour changes.
`_cwd` is a required ordering-only input (wired from `check-suite-cwd`); the `= None`
default keeps the signature valid since it follows defaulted ports.

```
contract: unit
inputs:   logs_dir:str = "logs", env_ready:bool = True, _cwd:Path
outputs:  default → bool   (always True; sequencing only)
```

```python
class EnsureLogsDirMod:
    def run(self, logs_dir:str = "logs", env_ready:bool = True, _cwd:Path = None):
        Path(logs_dir).mkdir(parents=True, exist_ok=True)   # OSError/PermissionError → harness CRITICAL
        log.info("logs_dir_ready", path=str(Path(logs_dir).resolve()))
        return ("default", True)
```

## Algorithm

1. Create the directory idempotently: `Path(logs_dir).mkdir(parents=True, exist_ok=True)` —
   `exist_ok=True` makes re-runs a no-op; `parents=True` accepts nested paths like
   `build/logs`. The `_cwd` and `env_ready` inputs are ordering-only — never read or branched
   on; they exist so the harness sequences this node after `check-suite-cwd` and
   `prepend-cwd-path`.
2. Record it for auditability: `log.info("logs_dir_ready",
   path=str(Path(logs_dir).resolve()))`.
3. Emit `("default", True)` — a sequencing token chained to `cc-run.env_ready` /
   `sim-run.env_ready`. The path is **not** stamped into `ctx`; downstream writers
   (`build-compile-cmd`/`build-sim-cmd`/`resolve-seed`/`write-randseed`) recompose it from the
   same `logs_dir` persistent input at their use sites.
4. **Failure — unwritable parent.** A `PermissionError`/`OSError` from `mkdir` is a
   setup-domain config error, left to propagate uncaught (harness CRITICAL via the
   bubbling-SystemExit catch, same idiom as `DiscoverConfigFileMod`) — no port-routed fail.

## Deliverables

In `modules/rtl_buddy/setup.py`:

- `EnsureLogsDirMod` — bootstraps the CWD-relative artefact directory consumed by
  `cc-run`, `sim-run`, `write-randseed`, and `resolve-seed` (REPLAY). Mirrors
  `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` (`output_dir = "logs"; if not
  os.path.exists(...): os.makedirs(...)`), but lifted out of `VlogSim.__init__`'s
  per-test lazy mkdir into a single explicit setup node so:
  (i) no downstream writer needs its own `mkdir`, and
  (ii) the directory is created exactly once per invocation, ahead of any subprocess.
  Takes the CLI `logs_dir:str` (default `"logs"`; `rtl_buddy` has no override, this is a
  small Notable divergence — see [07](../07-ambiguities-and-assumptions.md)), plus two
  sequencing inputs: `env_ready:bool` from `prepend-cwd-path` (so the `$PATH` mutation
  precedes us) and `_cwd:Path` from `check-suite-cwd` (so we never create `logs/` in an
  invalid CWD that the check would have aborted). Zero side-effects on the latter — it
  is consumed solely for data-edge ordering. Runs once via `unit`. See
  [Algorithm](#algorithm) for the numbered steps.
  Path is **not** resolved-and-stamped into `ctx`. Downstream paths are composed in
  `build-compile-cmd` / `build-sim-cmd` / `resolve-seed` / `write-randseed` from the same
  `logs_dir` persistent input, so the path joins happen at the use site. The two legs name
  files differently:
  - **compile leg** (`build-compile-cmd`, spec [07a](07a-build-compile-cmd.md)):
    `f"{logs_dir}/{test_tag}.compile.log"` and `.compile.err`, where
    `test_tag = re.sub(r"[^A-Za-z0-9_.-]", "_", test_name)` — the **sanitised** build tag
    (rtl_buddy `_get_build_tag`, `tools/vlog_sim.py:61-65`). Example: test `my_test` →
    `logs/my_test.compile.log`.
  - **sim leg** (`build-sim-cmd` / `resolve-seed` / `write-randseed`, specs
    [08c](08c-build-sim-cmd.md) / [08b](08b-resolve-seed.md) / [08d](08d-write-randseed.md)):
    `f"{logs_dir}/{test_name}{run_suffix}.log"`, `.err`, and `.randseed`, off the **raw**
    `test_name`, where `run_suffix` is `""` when `ctx["run_id"] is None` and
    `f"_{run_id:04d}"` (the run-id zero-padded to four digits) otherwise — rtl_buddy
    `_get_log_path` (`tools/vlog_sim.py:82-86`). Examples: a single run of `my_test` →
    `logs/my_test.log`; run-id 3 → `logs/my_test_0003.randseed`.
  **Failure handling**: `PermissionError` / `OSError` from `mkdir` propagate uncaught
  (becomes a harness CRITICAL via the bubbling-SystemExit catch, same idiom as
  `DiscoverConfigFileMod`'s `PermissionError`). No port-routed fail — this is a setup-domain
  config error, not per-test.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` — the `output_dir = "logs"` mkdir in `VlogSim.__init__` (lifted to a setup node).

**Manifest** — append to the `- file: rtl_buddy/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: ensure-logs-dir, class_name: EnsureLogsDirMod }
```

## Tests

In `modules/tests/test_setup.py`. Fixtures: `tmp_path` + `monkeypatch.chdir` for the CWD;
`logging_handler` for the failure path.

- `logs_dir="logs"`, no pre-existing `logs/` → emits `("default", True)` and `logs/` now
  exists under CWD.
- `logs_dir="logs"` with a pre-existing `logs/` → emits `("default", True)`, no exception
  (idempotent via `exist_ok=True`).
- `logs_dir="build/logs"`, no pre-existing `build/` → emits `("default", True)` and both
  `build/` and `build/logs/` now exist (boundary: nested, verifies `parents=True`).
- `logs_dir="/abs/path/logs"` (absolute) → emits `("default", True)` and the absolute path
  now exists (downstream `cc-build`/`sim-build` compose the same prefix).
- `logs_dir` pointing into a read-only parent → `mkdir` raises `PermissionError`, propagates
  uncaught → `pytest.raises(PermissionError)` (mirrors `DiscoverConfigFileMod`).

## Acceptance criteria

- Tests pass.
- Output port `default` exercised: emits `True` and leaves the configured `logs_dir` present
  on disk (default `./logs/`) before any later main-line node fires (contributes to the
  setup-only end-to-end graph — see [04 index](04-setup-modules.md#acceptance-criteria)).
- Failure idiom exercised: an `OSError`/`PermissionError` creating `logs_dir` bubbles to the
  harness CRITICAL handler (exit 1).
- The `modules/config.yaml` manifest entry `{ name: ensure-logs-dir, class_name: EnsureLogsDirMod }`
  validates and the harness resolves `ensure-logs-dir` → `EnsureLogsDirMod`.

## Constraints

- `unit` contract, runs once — create the directory with `Path(logs_dir).mkdir(parents=True,
  exist_ok=True)` (idempotent; nested paths allowed).
- `_cwd` and `env_ready` are **ordering-only** inputs — never read, branch on, or mutate them;
  they exist solely so the harness sequences this node after `check-suite-cwd` and
  `prepend-cwd-path`.
- Do **not** stamp the path into `ctx` — downstream writers
  (`build-compile-cmd`/`build-sim-cmd`/`resolve-seed`/`write-randseed`) recompose it from the
  same `logs_dir` persistent input at their use sites.
- `PermissionError`/`OSError` from `mkdir` propagate uncaught (harness CRITICAL) — no
  port-routed fail; this is a setup-domain error, not per-test.
- Emit `("default", True)` as a sequencing token only.

## Notes

`EnsureLogsDirMod` is wired in `test`/`randtest` only: regression's per-suite `chdir`
means a once-at-startup `logs/` bootstrap targets the wrong place; the regression
equivalent runs **per chdir'd suite** and is owned by [08](../08-sibling-graphs.md).

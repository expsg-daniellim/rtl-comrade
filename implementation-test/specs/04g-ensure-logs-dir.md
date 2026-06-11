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
`a69d962`). This module appends to `modules/rtl_test/setup.py`, shared with the setup chain
(`04a`–`04i`, index [04](04-setup-modules.md)), the selection/expansion chain (`05a`–`05f`,
index [05](05-selection-expansion-modules.md)), and git-status (`10b`); coordinate shared
imports and helpers with those specs.

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

## Deliverables

In `modules/rtl_test/setup.py`:

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
  is consumed solely for data-edge ordering. Runs once via `unit`.
  **Behaviour**:
  1. `Path(logs_dir).mkdir(parents=True, exist_ok=True)` — idempotent; `parents=True`
     accepts nested paths (e.g., `build/logs`).
  2. `log.info("logs_dir_ready", path=str(Path(logs_dir).resolve()))` for auditability.
  3. Return `{"default": True}` so `cc-run.env_ready` and `sim-run.env_ready` can chain
     off the same sequencing surface as PATH-prepend (see [07 settled 25 / 26](../07-ambiguities-and-assumptions.md)).
  Path is **not** resolved-and-stamped into `ctx`. Downstream paths (`logs/<test>.compile.log`,
  `logs/<test>[_NNNN].log`/`.err`/`.randseed`) are composed in `build-compile-cmd` /
  `build-sim-cmd` / `resolve-seed` / `write-randseed` from the same `logs_dir` persistent
  input, so the path joins happen at the use site.
  **Failure handling**: `PermissionError` / `OSError` from `mkdir` propagate uncaught
  (becomes a harness CRITICAL via the bubbling-SystemExit catch, same idiom as
  `DiscoverConfigFileMod`'s `PermissionError`). No port-routed fail — this is a setup-domain
  config error, not per-test.
  **Compatibility source:** `rtl_buddy/src/rtl_buddy/tools/vlog_sim.py:55-59` — the `output_dir = "logs"` mkdir in `VlogSim.__init__` (lifted to a setup node).

**Manifest** — append to the `- file: rtl_test/setup.py` block in `modules/config.yaml`
(opened by [`04a`](04a-discover-config-file.md); append, don't re-create):

```yaml
  - { name: ensure-logs-dir, class_name: EnsureLogsDirMod }
```

## Tests

In `modules/tests/test_setup.py`:

- With `logs_dir="logs"` and no pre-existing `logs/` → `run()` creates `logs/` under CWD
  and returns `{"default": True}`.
- With a pre-existing `logs/` directory → `run()` is a no-op and still returns
  `{"default": True}` (idempotent, no exception).
- With `logs_dir="build/logs"` and no pre-existing `build/` → `run()` creates both
  `build/` and `build/logs/` (verifies `parents=True`).
- With `logs_dir="/abs/path/logs"` (absolute) → `run()` creates the absolute path;
  `cc-build` / `sim-build` downstream compose the same prefix.
- With `logs_dir` pointing into a read-only parent → `PermissionError` propagates uncaught
  (mirrors the `DiscoverConfigFileMod` PermissionError test).

## Acceptance criteria

- Tests pass.
- `EnsureLogsDirMod` leaves the configured `logs_dir` present on disk (default `./logs/`)
  before any later main-line node fires (contributes to the setup-only end-to-end graph —
  see [04 index](04-setup-modules.md#acceptance-criteria)).

## Notes

`EnsureLogsDirMod` is wired in `test`/`randtest` only: regression's per-suite `chdir`
means a once-at-startup `logs/` bootstrap targets the wrong place; the regression
equivalent runs **per chdir'd suite** and is owned by [08](../08-sibling-graphs.md).
